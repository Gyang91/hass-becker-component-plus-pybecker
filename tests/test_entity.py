"""Tests for the shared Becker stick entity base class."""

from unittest.mock import MagicMock

from custom_components.becker.binary_sensor import BeckerConnectionBinarySensor
from custom_components.becker.button import BeckerPairButton
from custom_components.becker.entity import BeckerStickEntity
from custom_components.becker.event import BeckerRemoteEvent


def _becker(available: bool) -> MagicMock:
    becker = MagicMock()
    becker.communicator.is_available.return_value = available
    return becker


def test_base_entity_follows_communicator_availability() -> None:
    becker = _becker(True)
    entity = BeckerStickEntity(becker, "entry-1")

    assert entity.available is True
    becker.communicator.is_available.return_value = False
    assert entity.available is False


def test_availability_change_refreshes_state() -> None:
    entity = BeckerStickEntity(_becker(True), "entry-1")
    entity.schedule_update_ha_state = MagicMock()

    entity._handle_availability()

    entity.schedule_update_ha_state.assert_called_once()


def test_stick_entities_share_the_base_class() -> None:
    for cls in (BeckerPairButton, BeckerRemoteEvent, BeckerConnectionBinarySensor):
        assert issubclass(cls, BeckerStickEntity)


def test_remote_events_unavailable_without_connection() -> None:
    event = BeckerRemoteEvent(_becker(False), "entry-1")

    assert event.available is False


def test_connection_sensor_stays_available_without_connection() -> None:
    """A lost connection must show as off, not as unavailable."""
    sensor = BeckerConnectionBinarySensor(_becker(False), "entry-1")

    assert sensor.available is True
    assert sensor.is_on is False
