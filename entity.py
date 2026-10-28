"""Shared base for Becker entities that depend on the Centronic stick."""

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import availability_signal_for_entry


class BeckerStickEntity(Entity):
    """Entity whose availability follows the Centronic stick.

    It is available while the communicator can accept RF work and refreshes
    its state whenever the stick connects or disconnects.
    """

    _attr_has_entity_name = True

    def __init__(self, becker, entry_id: str) -> None:
        """Remember the stick and the config entry it belongs to."""
        self._becker = becker
        self._entry_id = entry_id

    @property
    def available(self) -> bool:
        """Return whether the Becker communicator is currently available."""
        return self._becker.communicator.is_available()

    async def async_added_to_hass(self) -> None:
        """Subscribe to communicator availability changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                availability_signal_for_entry(self._entry_id),
                self._handle_availability,
            )
        )

    @callback
    def _handle_availability(self) -> None:
        """Refresh state after a communicator availability change."""
        self.schedule_update_ha_state()
