"""Binary sensor platform for Becker connectivity."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .entity import BeckerStickEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Becker connection binary sensor."""
    async_add_entities([BeckerConnectionBinarySensor(entry.runtime_data, entry.entry_id)])


class BeckerConnectionBinarySensor(BeckerStickEntity, BinarySensorEntity):
    """Expose the Centronic stick connection state."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, becker, entry_id: str) -> None:
        """Initialize the connection sensor."""
        super().__init__(becker, entry_id)
        self._attr_unique_id = f"{entry_id}_connection"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})

    @property
    def available(self) -> bool:
        """Stay available so a lost connection shows as off, not unavailable."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the Becker communicator is available."""
        return self._becker.communicator.is_available()
