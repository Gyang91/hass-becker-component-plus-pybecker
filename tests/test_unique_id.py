"""Tests for stick-scoped unique ids and their migration."""

import logging

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.const import ATTR_ASSUMED_STATE, CONF_DEVICE, CONF_FILENAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.becker import _migrate_unique_ids
from custom_components.becker.const import (
    CONF_CHANNEL,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_DB_FILENAME,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
)


def _stick_entry(device: str, channel: str, name: str) -> MockConfigEntry:
    """Return a stick config entry with one cover on the given channel."""
    return MockConfigEntry(
        title=f"Becker ({device})",
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_DEVICE: device,
            CONF_FILENAME: DEFAULT_DB_FILENAME,
        },
        unique_id=device,
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_COVER,
                "title": name,
                "unique_id": channel,
                "data": {CONF_CHANNEL: channel, "friendly_name": name},
            }
        ],
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _register_old(
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    domain: str,
    unique_id: str,
    entity_id: str,
) -> er.RegistryEntry:
    """Register an entity the way 1.0.6 and older did (bare channel ids)."""
    subentry_id = next(iter(entry.subentries))
    return entity_registry.async_get_or_create(
        domain,
        DOMAIN,
        unique_id,
        config_entry=entry,
        config_subentry_id=subentry_id,
        suggested_object_id=entity_id.split(".", 1)[1],
    )


@pytest.mark.usefixtures("mock_becker")
async def test_new_covers_use_stick_scoped_ids(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """New covers and pair buttons get unique ids that include the stick."""
    await _setup(hass, mock_config_entry_with_cover)
    entry_id = mock_config_entry_with_cover.entry_id

    assert entity_registry.async_get_entity_id(
        "cover", DOMAIN, f"{entry_id}_1"
    ) == "cover.kitchen"
    assert entity_registry.async_get_entity_id(
        "button", DOMAIN, f"{entry_id}_1_pair"
    ) is not None
    assert entity_registry.async_get_entity_id("cover", DOMAIN, "1") is None


@pytest.mark.usefixtures("mock_becker")
async def test_old_ids_are_migrated_keeping_entity_ids(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Existing entities keep their entity id, settings and history key."""
    entry = mock_config_entry_with_cover
    entry.add_to_hass(hass)
    old_cover = _register_old(entity_registry, entry, "cover", "1", "cover.my_kitchen")
    old_button = _register_old(
        entity_registry, entry, "button", "1_pair", "button.my_kitchen_pair"
    )
    # A user customisation that must survive the migration.
    entity_registry.async_update_entity(old_cover.entity_id, name="Renamed")

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cover = entity_registry.async_get(old_cover.entity_id)
    assert cover.unique_id == f"{entry.entry_id}_1"
    assert cover.name == "Renamed"
    assert cover.id == old_cover.id
    button = entity_registry.async_get(old_button.entity_id)
    assert button.unique_id == f"{entry.entry_id}_1_pair"
    # No duplicate entities were created next to the migrated ones.
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert [e.entity_id for e in entities if e.domain == "cover"] == [
        old_cover.entity_id
    ]
    assert [e.entity_id for e in entities if e.domain == "button"] == [
        old_button.entity_id
    ]
    assert hass.states.get(old_cover.entity_id) is not None


@pytest.mark.usefixtures("mock_becker")
async def test_migration_is_idempotent(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Reloading after the migration changes nothing."""
    entry = mock_config_entry_with_cover
    entry.add_to_hass(hass)
    old_cover = _register_old(entity_registry, entry, "cover", "1", "cover.kitchen")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    after = {
        e.entity_id: e.unique_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    assert after == before
    assert after[old_cover.entity_id] == f"{entry.entry_id}_1"


@pytest.mark.usefixtures("mock_becker")
async def test_migration_skips_taken_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """An old entity is left alone if its new id already exists."""
    entry = mock_config_entry_with_cover
    entry.add_to_hass(hass)
    old_cover = _register_old(entity_registry, entry, "cover", "1", "cover.old_kitchen")
    taken = _register_old(
        entity_registry, entry, "cover", f"{entry.entry_id}_1", "cover.kitchen"
    )
    caplog.set_level(logging.WARNING, logger="custom_components.becker")

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get(old_cover.entity_id).unique_id == "1"
    assert entity_registry.async_get(taken.entity_id).unique_id == f"{entry.entry_id}_1"
    assert "already in use" in caplog.text


@pytest.mark.usefixtures("mock_becker")
async def test_migration_leaves_other_sticks_alone(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Only the entities of the stick being set up are migrated."""
    first = _stick_entry("/dev/ttyUSB0", "1", "Kitchen")
    second = _stick_entry("/dev/ttyUSB1", "1", "Garage")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    old_first = _register_old(entity_registry, first, "cover", "1", "cover.kitchen")

    # Migrating the second stick must not touch the first stick's entity,
    # although both use channel "1". (Setting up one entry would load all
    # entries of the domain, so call the migration directly.)
    _migrate_unique_ids(hass, second)

    assert entity_registry.async_get(old_first.entity_id).unique_id == "1"
    _migrate_unique_ids(hass, first)
    assert (
        entity_registry.async_get(old_first.entity_id).unique_id
        == f"{first.entry_id}_1"
    )


@pytest.mark.usefixtures("mock_becker")
async def test_two_sticks_can_use_the_same_channel(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Covers on the same channel of two sticks both get created."""
    first = _stick_entry("/dev/ttyUSB0", "1", "Kitchen")
    second = _stick_entry("/dev/ttyUSB1", "1", "Garage")
    await _setup(hass, first)
    await _setup(hass, second)

    assert hass.states.get("cover.kitchen") is not None
    assert hass.states.get("cover.garage") is not None
    covers = [
        e for e in entity_registry.entities.values()
        if e.platform == DOMAIN and e.domain == "cover"
    ]
    assert len(covers) == 2
    buttons = [
        e for e in entity_registry.entities.values()
        if e.platform == DOMAIN and e.domain == "button"
    ]
    assert len(buttons) == 2


@pytest.mark.usefixtures("mock_becker")
async def test_cover_reports_assumed_state(
    hass: HomeAssistant,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """The cover position is estimated, so both buttons stay usable."""
    await _setup(hass, mock_config_entry_with_cover)
    assert hass.states.get("cover.kitchen").attributes[ATTR_ASSUMED_STATE] is True
