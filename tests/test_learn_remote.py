"""Tests for learning a physical remote in the cover reconfigure flow."""

import asyncio
import re
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_DEVICE, CONF_FILENAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.becker import signal_for_entry
from custom_components.becker.config_flow import _add_remote_id, _PressCounter
from custom_components.becker.const import (
    CONF_CHANNEL,
    CONF_CONNECTION_TYPE,
    CONF_LEARN_REMOTE,
    CONF_REMOTE_ID,
    CONNECTION_TYPE_SERIAL,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
)
from custom_components.becker.pybecker.becker_helper import MESSAGE

STOP = "1"
UP = "2"
RELEASE = "0"

SETTINGS = {
    "friendly_name": "Kitchen window",
    "intermediate_position": True,
    "intermediate_position_up": 25,
    "intermediate_position_down": 75,
    "tilt_blind": False,
    "tilt_time_blind": 0.3,
}


def _packet(unit_id: str, channel: str, command: str) -> re.Match[bytes]:
    """Build a received packet."""
    body = (
        b"0000000002010B"
        + b"0001"
        + b"000000"
        + unit_id.encode()
        + b"000000"
        + channel.encode()
        + b"00"
        + command.encode()
        + b"0"
        + b"00"
    )
    match = MESSAGE.search(b"\x02" + body + b"\x03")
    assert match is not None
    return match


async def _send(hass: HomeAssistant, entry: MockConfigEntry, packet) -> None:
    """Deliver one packet without waiting for the listening task to end."""
    async_dispatcher_send(hass, signal_for_entry(entry.entry_id), packet)
    await asyncio.sleep(0)


async def _press(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    unit_id: str = "1737B",
    channel: str = "2",
    button: str = STOP,
) -> None:
    """Press and release one button on a remote."""
    await _send(hass, entry, _packet(unit_id, channel, button))
    await _send(hass, entry, _packet(unit_id, channel, RELEASE))


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry, title=None):
    subentry = next(
        s for s in entry.subentries.values() if title is None or s.title == title
    )
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_COVER),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    return subentry.subentry_id, result


async def _start_listening(hass, entry, extra=None, title=None):
    subentry_id, result = await _start_reconfigure(hass, entry, title)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**SETTINGS, **(extra or {}), CONF_LEARN_REMOTE: True}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["step_id"] == "learn_remote"
    return subentry_id, result["flow_id"]


def _step(hass: HomeAssistant, flow_id: str) -> str:
    return hass.config_entries.subentries.async_get(flow_id)["step_id"]


async def _result(hass: HomeAssistant, flow_id: str):
    """Return the flow's current screen once listening has finished."""
    await hass.async_block_till_done()
    return await hass.config_entries.subentries.async_configure(flow_id)


async def _choose(hass: HomeAssistant, flow_id: str, option: str):
    return await hass.config_entries.subentries.async_configure(
        flow_id, {"next_step_id": option}
    )


async def _let_listening_time_out(hass: HomeAssistant) -> None:
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()


async def _stop_listening(hass: HomeAssistant, flow_id: str) -> None:
    """Close the dialog so a still-listening test ends without the timeout."""
    hass.config_entries.subentries.async_abort(flow_id)
    await hass.async_block_till_done()


def _two_cover_entry() -> MockConfigEntry:
    """A stick with Kitchen (no remote) and Living room (follows 1737B:2)."""
    return MockConfigEntry(
        title="Becker (ttyUSB0)",
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_DEVICE: "/dev/ttyUSB0",
            CONF_FILENAME: "centronic-stick.db",
        },
        unique_id="/dev/ttyUSB0",
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_COVER,
                "title": "Kitchen",
                "unique_id": "1",
                "data": {CONF_CHANNEL: "1", "friendly_name": "Kitchen"},
            },
            {
                "subentry_type": SUBENTRY_TYPE_COVER,
                "title": "Living room",
                "unique_id": "2",
                "data": {
                    CONF_CHANNEL: "2",
                    "friendly_name": "Living room",
                    CONF_REMOTE_ID: "1737b:2",
                },
            },
        ],
    )


@pytest.mark.usefixtures("mock_becker")
async def test_two_stop_presses_offer_the_remote(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Two STOP presses show what was heard; linking saves it."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(hass, entry)

    await _press(hass, entry)
    assert _step(hass, flow_id) == "learn_remote"
    await _press(hass, entry)

    result = await _result(hass, flow_id)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "learn_remote_confirm"
    assert result["menu_options"] == [
        "learn_remote_link",
        "learn_remote",
        "save_without_remote",
    ]
    assert result["description_placeholders"] == {
        "buttons": "■ STOP, ■ STOP",
        "remote_id": "1737B",
        "remote_channel": "2",
        "covers": "",
    }

    result = await _choose(hass, flow_id, "learn_remote_link")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    data = entry.subentries[subentry_id].data
    assert data[CONF_REMOTE_ID] == "1737B:2"
    assert data["friendly_name"] == "Kitchen window"
    assert data[CONF_CHANNEL] == "1"
    assert CONF_LEARN_REMOTE not in data


@pytest.mark.usefixtures("mock_becker")
async def test_buttons_heard_are_shown(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """A remote without STOP: the UP presses are shown as such."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)
    await _press(hass, entry, button=UP)
    await _press(hass, entry, button=UP)

    result = await _result(hass, flow_id)
    assert result["description_placeholders"]["buttons"] == "▲ UP, ▲ UP"


@pytest.mark.usefixtures("mock_becker")
async def test_held_button_is_one_press(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Repeated packets of a held button do not count as a second press."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)

    for _ in range(3):
        await _send(hass, entry, _packet("1737B", "2", STOP))
    await _send(hass, entry, _packet("1737B", "2", RELEASE))
    assert _step(hass, flow_id) == "learn_remote"

    await _press(hass, entry)
    result = await _result(hass, flow_id)
    assert result["step_id"] == "learn_remote_confirm"


@pytest.mark.usefixtures("mock_becker")
async def test_single_press_is_not_enough(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """One press keeps listening."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)
    await _press(hass, entry)
    assert _step(hass, flow_id) == "learn_remote"
    await _stop_listening(hass, flow_id)


@pytest.mark.usefixtures("mock_becker")
async def test_single_presses_of_two_remotes_do_not_match(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """One press each from two remotes is not enough; the remote pressed twice wins."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)

    await _press(hass, entry, unit_id="1737B")
    await _press(hass, entry, unit_id="2A2A2")
    assert _step(hass, flow_id) == "learn_remote"

    await _press(hass, entry, unit_id="1737B")
    result = await _result(hass, flow_id)
    assert result["description_placeholders"]["remote_id"] == "1737B"


@pytest.mark.usefixtures("mock_becker")
async def test_all_channels_button_is_ignored(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Presses on the all-channels setting ("F") are not counted."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)

    await _press(hass, entry, channel="F")
    await _press(hass, entry, channel="F")
    assert _step(hass, flow_id) == "learn_remote"

    await _press(hass, entry, channel="3")
    await _press(hass, entry, channel="3")
    result = await _result(hass, flow_id)
    assert result["description_placeholders"]["remote_channel"] == "3"


@pytest.mark.usefixtures("mock_becker")
async def test_remote_already_linked_to_this_cover(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Hearing a remote the cover already follows adds nothing."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(
        hass, entry, {CONF_REMOTE_ID: "1737b:2"}
    )
    await _press(hass, entry)
    await _press(hass, entry)

    result = await _result(hass, flow_id)
    assert result["step_id"] == "learn_remote_known"
    assert result["menu_options"] == ["save_without_remote", "learn_remote"]

    await _choose(hass, flow_id, "save_without_remote")
    await hass.async_block_till_done()
    assert entry.subentries[subentry_id].data[CONF_REMOTE_ID] == "1737b:2"


@pytest.mark.usefixtures("mock_becker")
async def test_remote_linked_to_another_cover_is_named(
    hass: HomeAssistant,
) -> None:
    """The user is told which other cover already follows the remote."""
    entry = _two_cover_entry()
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(hass, entry, title="Kitchen")
    await _press(hass, entry)
    await _press(hass, entry)

    result = await _result(hass, flow_id)
    assert result["step_id"] == "learn_remote_confirm_linked"
    assert result["description_placeholders"]["covers"] == "Living room"

    # Linking anyway is allowed: one remote channel may drive several covers.
    await _choose(hass, flow_id, "learn_remote_link")
    await hass.async_block_till_done()
    assert entry.subentries[subentry_id].data[CONF_REMOTE_ID] == "1737B:2"


@pytest.mark.usefixtures("mock_becker")
async def test_listen_again_from_result(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """If the buttons shown are not what the user pressed, they can listen again."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(hass, entry)
    await _press(hass, entry, unit_id="2A2A2", button=UP)
    await _press(hass, entry, unit_id="2A2A2", button=UP)
    await _result(hass, flow_id)

    result = await _choose(hass, flow_id, "learn_remote")
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await _press(hass, entry)
    await _press(hass, entry)
    result = await _result(hass, flow_id)
    assert result["description_placeholders"]["remote_id"] == "1737B"

    await _choose(hass, flow_id, "learn_remote_link")
    await hass.async_block_till_done()
    assert entry.subentries[subentry_id].data[CONF_REMOTE_ID] == "1737B:2"


@pytest.mark.usefixtures("mock_becker")
async def test_save_without_linking_from_result(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """The other settings can be saved without linking what was heard."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(hass, entry)
    await _press(hass, entry)
    await _press(hass, entry)
    await _result(hass, flow_id)

    result = await _choose(hass, flow_id, "save_without_remote")
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    data = entry.subentries[subentry_id].data
    assert data["friendly_name"] == "Kitchen window"
    assert CONF_REMOTE_ID not in data


@pytest.mark.usefixtures("mock_becker")
async def test_timeout_then_retry_then_save(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """With no presses, the user can listen again or save the other settings."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    with patch("custom_components.becker.config_flow.LEARN_REMOTE_TIMEOUT", 0.01):
        subentry_id, flow_id = await _start_listening(hass, entry)
        await _let_listening_time_out(hass)
        result = await hass.config_entries.subentries.async_configure(flow_id)
        assert result["type"] is FlowResultType.MENU
        assert result["step_id"] == "learn_remote_failed"

        result = await _choose(hass, flow_id, "learn_remote")
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        await _let_listening_time_out(hass)
        result = await hass.config_entries.subentries.async_configure(flow_id)
        assert result["step_id"] == "learn_remote_failed"

    result = await _choose(hass, flow_id, "save_without_remote")
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[subentry_id].data["friendly_name"] == "Kitchen window"


@pytest.mark.usefixtures("mock_becker")
async def test_learning_sends_nothing(
    hass: HomeAssistant,
    mock_becker: MagicMock,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Learning only listens: no RF command is sent to any cover."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    mock_becker.reset_mock()
    _, flow_id = await _start_listening(hass, entry)
    await _press(hass, entry)
    await _press(hass, entry)
    await _result(hass, flow_id)
    await _choose(hass, flow_id, "learn_remote_link")
    await hass.async_block_till_done()

    for name in ("move_up", "move_down", "stop", "pair", "send"):
        getattr(mock_becker, name).assert_not_called()


async def test_learning_requires_loaded_stick(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Without a connected stick nothing can be heard, so say so up front."""
    entry = mock_config_entry_with_cover
    entry.add_to_hass(hass)
    _, result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**SETTINGS, CONF_LEARN_REMOTE: True}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_loaded"}


@pytest.mark.usefixtures("mock_becker")
async def test_closing_dialog_stops_listening(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Abandoning the flow while listening leaves nothing running."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)
    await _press(hass, entry)

    await _stop_listening(hass, flow_id)
    # Later presses reach no listener and change nothing.
    await _press(hass, entry)
    await _press(hass, entry)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_becker")
async def test_reconfigure_without_learning_does_not_store_flag(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """The checkbox is a one-off action, not a stored setting."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**SETTINGS, CONF_LEARN_REMOTE: False}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert CONF_LEARN_REMOTE not in entry.subentries[subentry_id].data


def test_press_counter() -> None:
    """Separate presses count; held repeats do not; a long gap starts a press."""
    counter = _PressCounter()
    assert counter.add("A:1", "halt", 0.0) == ["■ STOP"]
    assert counter.add("A:1", "halt", 0.2) == ["■ STOP"]  # held
    assert counter.add("A:1", "release", 0.3) == ["■ STOP"]
    assert counter.add("A:1", "halt", 0.5) == ["■ STOP", "■ STOP"]  # released before

    counter = _PressCounter()
    counter.add("A:1", "up", 0.0)
    # Release missed, but nothing was heard for a while: a new press.
    assert counter.add("A:1", "down", 2.0) == ["▲ UP", "▼ DOWN"]

    counter = _PressCounter()
    counter.add("A:1", "halt", 0.0)
    assert counter.add("B:1", "halt", 0.1) == ["■ STOP"]  # counted per remote
    assert counter.add("A:1", "unknown", 5.0) == ["■ STOP", "unknown"]


@pytest.mark.parametrize(
    ("existing", "learned", "expected"),
    [
        (None, "1737B:2", "1737B:2"),
        ("", "1737B:2", "1737B:2"),
        ("12345:1", "1737B:2", "12345:1, 1737B:2"),
        ("12345:1,1737b:2", "1737B:2", "12345:1, 1737b:2"),
    ],
)
def test_add_remote_id(existing, learned, expected) -> None:
    assert _add_remote_id(existing, learned) == expected
