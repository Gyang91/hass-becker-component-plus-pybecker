"""Tests for remembering channels of removed covers."""

from typing import Any

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.becker import async_known_channels
from custom_components.becker.const import CONF_CHANNEL, DOMAIN, SUBENTRY_TYPE_COVER


def _key(entry: MockConfigEntry) -> str:
    return f"{DOMAIN}.{entry.entry_id}.channels"


def _seed(hass_storage: dict[str, Any], entry: MockConfigEntry, channels) -> None:
    """Pretend covers on these channels existed before (and some were removed)."""
    hass_storage[_key(entry)] = {
        "version": 1,
        "minor_version": 1,
        "key": _key(entry),
        "data": {"channels": channels},
    }


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _open_add_cover(hass: HomeAssistant, entry: MockConfigEntry):
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_COVER), context={"source": SOURCE_USER}
    )


def _suggested_channel(result) -> str | None:
    for marker in result["data_schema"].schema:
        if marker == CONF_CHANNEL:
            return (marker.description or {}).get("suggested_value")
    raise KeyError(CONF_CHANNEL)


@pytest.mark.usefixtures("mock_becker")
async def test_setup_remembers_cover_channels(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Every cover's channel is remembered, so it stays known after removal."""
    await _setup(hass, mock_config_entry_with_cover)
    assert await async_known_channels(hass, mock_config_entry_with_cover.entry_id) == [
        "1"
    ]


@pytest.mark.usefixtures("mock_becker")
async def test_removed_cover_channel_is_not_suggested(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Channel 2 belonged to a removed cover, so the form skips it."""
    entry = mock_config_entry_with_cover
    _seed(hass_storage, entry, ["1", "2"])
    await _setup(hass, entry)

    result = await _open_add_cover(hass, entry)
    assert _suggested_channel(result) == "3"


@pytest.mark.usefixtures("mock_becker")
async def test_reusing_a_removed_cover_channel_warns_once(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Typing a removed cover's channel warns; submitting it again keeps it."""
    entry = mock_config_entry_with_cover
    _seed(hass_storage, entry, ["1", "2:1"])
    await _setup(hass, entry)

    result = await _open_add_cover(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CHANNEL: "2:1"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CHANNEL: "channel_used_before"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CHANNEL: "2:1"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pair"


@pytest.mark.usefixtures("mock_becker")
async def test_unused_channel_needs_no_confirmation(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """A channel that was never used goes straight to pairing."""
    entry = mock_config_entry_with_cover
    _seed(hass_storage, entry, ["1", "2"])
    await _setup(hass, entry)

    result = await _open_add_cover(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_CHANNEL: "3"}
    )
    assert result["step_id"] == "pair"


@pytest.mark.usefixtures("mock_becker")
async def test_current_channel_is_still_rejected(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Submitting a channel in use twice never gets past the duplicate check."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    result = await _open_add_cover(hass, entry)
    for _ in range(2):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], {CONF_CHANNEL: "1:1"}
        )
        assert result["errors"] == {CONF_CHANNEL: "already_configured"}


@pytest.mark.usefixtures("mock_becker")
async def test_falls_back_to_removed_channels_when_stick_is_full(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """With every channel used at some point, a removed cover's channel is offered."""
    entry = mock_config_entry_with_cover
    _seed(
        hass_storage,
        entry,
        [f"{unit}:{channel}" for unit in range(1, 6) for channel in range(1, 8)],
    )
    await _setup(hass, entry)

    result = await _open_add_cover(hass, entry)
    assert _suggested_channel(result) == "2"


@pytest.mark.usefixtures("mock_becker")
async def test_deleting_the_stick_forgets_its_channels(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Removing the whole entry also removes its remembered channels."""
    entry = mock_config_entry_with_cover
    await _setup(hass, entry)
    assert await async_known_channels(hass, entry.entry_id) == ["1"]

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert await async_known_channels(hass, entry.entry_id) == []
