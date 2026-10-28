"""Button platform for the Becker integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_FRIENDLY_NAME, EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo, async_get_device_id_by_identifier

from .const import CONF_CHANNEL, DOMAIN, MANUFACTURER, SUBENTRY_TYPE_COVER
from .entity import BeckerStickEntity
from .pybecker.becker_helper import BeckerConnectionError

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up a pair button for each configured cover."""
    becker = entry.runtime_data
    parent_device_id = async_get_device_id_by_identifier(
        hass,
        (DOMAIN, entry.entry_id),
        config_entry_id=entry.entry_id,
    )
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_COVER:
            continue
        channel = subentry.data[CONF_CHANNEL]
        name = subentry.data.get(CONF_FRIENDLY_NAME) or f"Channel {channel}"
        async_add_entities(
            [BeckerPairButton(becker, entry.entry_id, channel, name, parent_device_id)],
            config_subentry_id=subentry_id,
        )


class BeckerPairButton(BeckerStickEntity, ButtonEntity):
    """Button that teaches a shutter receiver this stick's channel."""

    _attr_translation_key = "pair"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, becker, entry_id, channel, name, parent_device_id=None):
        """Init the pair button."""
        super().__init__(becker, entry_id)
        self._channel = channel
        self._attr_unique_id = f"{channel}_pair"
        # Share the cover's device so the button shows up on the cover. The
        # name is set here too because platforms set up concurrently and the
        # button may register before the cover names the device.
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{channel}")},
            name=name,
            manufacturer=MANUFACTURER,
        )
        if parent_device_id is not None:
            device_info["via_device_id"] = parent_device_id
        self._attr_device_info = device_info

    async def async_press(self):
        """Send the pairing (TRAIN) signal on the cover's channel."""
        try:
            await self._becker.pair(self._channel)
        except BeckerConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_failed",
            ) from err
