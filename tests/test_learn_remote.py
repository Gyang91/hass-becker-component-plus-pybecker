"""Tests for learning a physical remote in the cover reconfigure flow."""

import asyncio
import re
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.becker import signal_for_entry
from custom_components.becker.config_flow import _add_remote_id
from custom_components.becker.const import (
    CONF_CHANNEL,
    CONF_LEARN_REMOTE,
    CONF_REMOTE_ID,
    SUBENTRY_TYPE_COVER,
)
from custom_components.becker.pybecker.becker_helper import MESSAGE


def _make_packet(unit_id: str, channel: str, command: str = "1") -> re.Match[bytes]:
    """Build a received packet (default command: HALT/STOP)."""
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


SETTINGS = {
    "friendly_name": "Kitchen window",
    "intermediate_position": True,
    "intermediate_position_up": 25,
    "intermediate_position_down": 75,
    "tilt_blind": False,
    "tilt_time_blind": 0.3,
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry):
    subentry = next(iter(entry.subentries.values()))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_COVER),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    return subentry.subentry_id, result


async def _start_listening(hass: HomeAssistant, entry: MockConfigEntry, extra=None):
    subentry_id, result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**SETTINGS, **(extra or {}), CONF_LEARN_REMOTE: True}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["step_id"] == "learn_remote"
    return subentry_id, result["flow_id"]


async def _let_listening_time_out(hass: HomeAssistant) -> None:
    """Wait (for real) past the patched listening timeout."""
    await asyncio.sleep(0.05)
    await hass.async_block_till_done()


async def _hear(hass: HomeAssistant, entry: MockConfigEntry, packet) -> None:
    async_dispatcher_send(hass, signal_for_entry(entry.entry_id), packet)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_becker")
async def test_learn_remote_adds_heard_remote(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """A STOP press is turned into a remote id and saved with the settings."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(hass, entry)

    await _hear(hass, entry, _make_packet("1737B", "2"))
    result = await hass.config_entries.subentries.async_configure(flow_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "learn_remote_confirm"
    assert result["description_placeholders"] == {CONF_REMOTE_ID: "1737B:2"}

    result = await hass.config_entries.subentries.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    data = entry.subentries[subentry_id].data
    assert data[CONF_REMOTE_ID] == "1737B:2"
    assert data["friendly_name"] == "Kitchen window"
    assert data[CONF_CHANNEL] == "1"
    assert CONF_LEARN_REMOTE not in data


@pytest.mark.usefixtures("mock_becker")
async def test_learn_remote_appends_to_existing_remotes(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """A learned remote is added next to remotes already configured."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    subentry_id, flow_id = await _start_listening(
        hass, entry, {CONF_REMOTE_ID: "12345:1"}
    )

    await _hear(hass, entry, _make_packet("1737B", "2"))
    await hass.config_entries.subentries.async_configure(flow_id)
    await hass.config_entries.subentries.async_configure(flow_id, {})
    await hass.async_block_till_done()

    assert entry.subentries[subentry_id].data[CONF_REMOTE_ID] == "12345:1, 1737B:2"


@pytest.mark.usefixtures("mock_becker")
async def test_learn_remote_ignores_all_channels_button(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """The all-channels button ("F") is skipped; the next real press counts."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    _, flow_id = await _start_listening(hass, entry)

    # Not _hear(): waiting for all tasks would sit out the whole timeout.
    async_dispatcher_send(
        hass, signal_for_entry(entry.entry_id), _make_packet("1737B", "F")
    )
    await asyncio.sleep(0)
    # Still listening.
    assert hass.config_entries.subentries.async_get(flow_id)["step_id"] == "learn_remote"

    await _hear(hass, entry, _make_packet("1737B", "3"))
    result = await hass.config_entries.subentries.async_configure(flow_id)
    assert result["description_placeholders"] == {CONF_REMOTE_ID: "1737B:3"}


@pytest.mark.usefixtures("mock_becker")
async def test_learn_remote_timeout_then_save_without_remote(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """With no press, the other settings can still be saved."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    with patch("custom_components.becker.config_flow.LEARN_REMOTE_TIMEOUT", 0.01):
        subentry_id, flow_id = await _start_listening(hass, entry)
        await _let_listening_time_out(hass)
    result = await hass.config_entries.subentries.async_configure(flow_id)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "learn_remote_failed"

    result = await hass.config_entries.subentries.async_configure(
        flow_id, {"next_step_id": "save_without_remote"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    data = entry.subentries[subentry_id].data
    assert data["friendly_name"] == "Kitchen window"
    assert CONF_REMOTE_ID not in data
    assert CONF_LEARN_REMOTE not in data


@pytest.mark.usefixtures("mock_becker")
async def test_learn_remote_timeout_then_retry(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """After a timeout the user can listen again and succeed."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    with patch("custom_components.becker.config_flow.LEARN_REMOTE_TIMEOUT", 0.01):
        subentry_id, flow_id = await _start_listening(hass, entry)
        await _let_listening_time_out(hass)
    await hass.config_entries.subentries.async_configure(flow_id)

    result = await hass.config_entries.subentries.async_configure(
        flow_id, {"next_step_id": "learn_remote"}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS

    await _hear(hass, entry, _make_packet("1737B", "2"))
    await hass.config_entries.subentries.async_configure(flow_id)
    await hass.config_entries.subentries.async_configure(flow_id, {})
    await hass.async_block_till_done()
    assert entry.subentries[subentry_id].data[CONF_REMOTE_ID] == "1737B:2"


@pytest.mark.usefixtures("mock_becker")
async def test_learn_remote_sends_nothing(
    hass: HomeAssistant,
    mock_becker: MagicMock,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Learning only listens: no RF command is sent to any cover."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    mock_becker.reset_mock()
    _, flow_id = await _start_listening(hass, entry)
    await _hear(hass, entry, _make_packet("1737B", "2"))
    await hass.config_entries.subentries.async_configure(flow_id)
    await hass.config_entries.subentries.async_configure(flow_id, {})
    await hass.async_block_till_done()

    for name in ("move_up", "move_down", "stop", "pair", "send"):
        getattr(mock_becker, name).assert_not_called()


async def test_learn_remote_requires_loaded_stick(
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

    hass.config_entries.subentries.async_abort(flow_id)
    await hass.async_block_till_done()
    # A later press must not resurrect or crash anything.
    await _hear(hass, entry, _make_packet("1737B", "2"))


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
