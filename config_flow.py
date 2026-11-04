"""Config flow for the Becker integration."""

import asyncio
import logging
import os
import shutil
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_DEVICE,
    CONF_FILENAME,
    CONF_FRIENDLY_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.selector import (
    BooleanSelector,
    FileSelector,
    FileSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SerialPortSelector,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from . import async_known_channels, signal_for_entry
from .event import decode_event_type
from .const import (
    BACKUP_PREFIX,
    CHANNEL_PATTERN,
    CONF_CHANNEL,
    CONF_COMMAND_RETRY_DELAY,
    CONF_COMMAND_RETRY_MAX,
    CONF_CONNECTION_TYPE,
    CONF_COVERS,
    CONF_INTERMEDIATE_DISABLE,
    CONF_INTERMEDIATE_POSITION,
    CONF_INTERMEDIATE_POSITION_DOWN,
    CONF_INTERMEDIATE_POSITION_UP,
    CONF_LEARN_REMOTE,
    CONF_PAIR,
    CONF_QUEUE_SIZE,
    CONF_REMOTE_ID,
    CONF_STATE_TEXT,
    CONF_TILT_BLIND,
    CONF_TILT_INTERMEDIATE,
    CONF_TILT_TIME_BLIND,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    CONF_UPLOAD,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_COMMAND_RETRY_DELAY,
    DEFAULT_COMMAND_RETRY_MAX,
    DEFAULT_DB_FILENAME,
    DEFAULT_DEVICE,
    DEFAULT_QUEUE_SIZE,
    DEFAULT_TCP_PORT,
    DOMAIN,
    DOWNLOAD_LINK_TTL_MINUTES,
    DOWNLOAD_URL,
    INTERMEDIATE_POSITION,
    LEARN_REMOTE_PRESS_GAP,
    LEARN_REMOTE_PRESSES,
    LEARN_REMOTE_TIMEOUT,
    REMOTE_ID,
    SUBENTRY_TYPE_COVER,
    TILT_TIME,
    VENTILATION_POSITION,
)
from .pybecker.becker_helper import BeckerConnection, BeckerConnectionError

_LOGGER = logging.getLogger(__name__)

COVER_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FRIENDLY_NAME): TextSelector(),
        vol.Optional(CONF_VALUE_TEMPLATE): TemplateSelector(),
        vol.Optional(CONF_REMOTE_ID): TextSelector(),
        vol.Optional(CONF_TRAVELLING_TIME_DOWN): NumberSelector(
            NumberSelectorConfig(
                min=0, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
            )
        ),
        vol.Optional(CONF_TRAVELLING_TIME_UP): NumberSelector(
            NumberSelectorConfig(
                min=0, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
            )
        ),
        vol.Optional(CONF_INTERMEDIATE_POSITION, default=True): BooleanSelector(),
        vol.Optional(
            CONF_INTERMEDIATE_POSITION_UP, default=VENTILATION_POSITION
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=100, mode=NumberSelectorMode.BOX, unit_of_measurement="%"
            )
        ),
        vol.Optional(
            CONF_INTERMEDIATE_POSITION_DOWN, default=INTERMEDIATE_POSITION
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=100, mode=NumberSelectorMode.BOX, unit_of_measurement="%"
            )
        ),
        vol.Optional(CONF_TILT_INTERMEDIATE): BooleanSelector(),
        vol.Optional(CONF_TILT_BLIND, default=False): BooleanSelector(),
        vol.Optional(CONF_TILT_TIME_BLIND, default=TILT_TIME): NumberSelector(
            NumberSelectorConfig(
                min=0, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
            )
        ),
    }
)

COVER_ADD_SCHEMA = vol.Schema(
    {vol.Required(CONF_CHANNEL): TextSelector()}
).extend(COVER_OPTIONS_SCHEMA.schema)

COVER_RECONFIGURE_SCHEMA = COVER_OPTIONS_SCHEMA.extend(
    {vol.Optional(CONF_LEARN_REMOTE, default=False): BooleanSelector()}
)

PAIR_SCHEMA = vol.Schema(
    {vol.Required(CONF_PAIR, default=True): BooleanSelector()}
)


def _test_connection(device: str) -> None:
    """Open and close the connection to validate the device (blocking)."""
    BeckerConnection(device, strict=True).close()


def _validate_cover_input(
    user_input: dict[str, Any], require_channel: bool
) -> dict[str, str]:
    """Validate cover subentry user input."""
    errors: dict[str, str] = {}
    if require_channel and not CHANNEL_PATTERN.match(user_input[CONF_CHANNEL]):
        errors[CONF_CHANNEL] = "invalid_channel"
    remote_id = user_input.get(CONF_REMOTE_ID)
    if remote_id and not REMOTE_ID.search(remote_id.upper()):
        errors[CONF_REMOTE_ID] = "invalid_remote_id"
    return errors


def _add_remote_id(remote_ids: str | None, remote_id: str) -> str:
    """Append a remote id to a comma separated list, skipping duplicates."""
    known = [part.strip() for part in (remote_ids or "").split(",") if part.strip()]
    if remote_id.upper() in (part.upper() for part in known):
        return ", ".join(known)
    return ", ".join([*known, remote_id])


# How a heard button is shown to the user. Symbols match the remote's keys.
BUTTON_LABELS = {
    "halt": "■ STOP",
    "up": "▲ UP",
    "down": "▼ DOWN",
    "up_intermediate": "▲▲ UP (intermediate)",
    "down_intermediate": "▼▼ DOWN (intermediate)",
}


def _remote_ids(remote_ids: str | None) -> set[str]:
    """Return the normalised ID:channel entries of a remote id setting."""
    return {
        f"{match['id']}:{match['ch']}"
        for match in REMOTE_ID.finditer((remote_ids or "").upper())
    }


class _PressCounter:
    """Count separate button presses per remote from received packets.

    A remote sends a button packet (possibly repeated while held) and a
    RELEASE packet when the button is let go. A packet starts a new press
    if the remote's previous press was released, or if nothing was heard
    from that remote for LEARN_REMOTE_PRESS_GAP seconds (a missed release).
    """

    def __init__(self) -> None:
        self._presses: dict[str, list[str]] = {}
        self._last_packet: dict[str, float] = {}
        self._released: set[str] = set()

    def add(self, remote_id: str, button: str, now: float) -> list[str]:
        """Record one packet; return the buttons pressed so far on that remote."""
        last = self._last_packet.get(remote_id)
        self._last_packet[remote_id] = now
        presses = self._presses.setdefault(remote_id, [])
        if button == "release":
            self._released.add(remote_id)
            return presses
        if (
            not presses
            or remote_id in self._released
            or last is None
            or now - last >= LEARN_REMOTE_PRESS_GAP
        ):
            presses.append(BUTTON_LABELS.get(button, button))
            self._released.discard(remote_id)
        return presses


def _channel_key(channel: str) -> tuple[int, int]:
    """Return (unit, channel) for a channel string.

    A bare channel uses sender unit 1, so "1" and "1:1" address the same
    receiver, as pybecker sends them.
    """
    unit, _, number = channel.rpartition(":")
    return int(unit or 1), int(number)


def _next_free_channel(used: list[str]) -> str | None:
    """Return the first USB stick channel no cover uses yet.

    Unit 1 is written as a bare channel ("1"), other units as "unit:channel".
    """
    taken = {_channel_key(channel) for channel in used}
    for unit in range(1, 6):
        for channel in range(1, 8):
            if (unit, channel) not in taken:
                return str(channel) if unit == 1 else f"{unit}:{channel}"
    return None


def _import_cover_data(slug: str, cover_config: dict[str, Any]) -> dict[str, Any]:
    """Map a validated YAML cover config onto subentry data."""
    data: dict[str, Any] = {CONF_CHANNEL: cover_config[CONF_CHANNEL]}
    for key in (
        CONF_FRIENDLY_NAME,
        CONF_REMOTE_ID,
        CONF_TRAVELLING_TIME_DOWN,
        CONF_TRAVELLING_TIME_UP,
        CONF_INTERMEDIATE_POSITION_UP,
        CONF_INTERMEDIATE_POSITION_DOWN,
        CONF_TILT_INTERMEDIATE,
        CONF_TILT_BLIND,
        CONF_TILT_TIME_BLIND,
    ):
        if key in cover_config:
            data[key] = cover_config[key]
    data.setdefault(CONF_FRIENDLY_NAME, slug)
    # Templates are not JSON serializable - store the template string
    if (template := cover_config.get(CONF_VALUE_TEMPLATE)) is not None:
        data[CONF_VALUE_TEMPLATE] = template.template
    # Collapse the deprecated intermediate_position_disable key
    intermediate_disable = cover_config.get(CONF_INTERMEDIATE_DISABLE, False)
    data[CONF_INTERMEDIATE_POSITION] = (
        cover_config.get(CONF_INTERMEDIATE_POSITION, True) and not intermediate_disable
    )
    return data


class BeckerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Becker Centronic stick."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_COVER: CoverSubentryFlowHandler}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the import/export options flow."""
        return BeckerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the connection type."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[CONNECTION_TYPE_SERIAL, CONNECTION_TYPE_NETWORK],
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a locally connected Centronic stick."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device = user_input[CONF_DEVICE]
            await self.async_set_unique_id(device)
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(_test_connection, device)
            except BeckerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Becker ({device.rsplit('/', 1)[-1]})",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                        CONF_DEVICE: device,
                        CONF_FILENAME: user_input.get(
                            CONF_FILENAME, DEFAULT_DB_FILENAME
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=DEFAULT_DEVICE): SerialPortSelector(),
                vol.Optional(
                    CONF_FILENAME, default=DEFAULT_DB_FILENAME
                ): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id=CONNECTION_TYPE_SERIAL, data_schema=schema, errors=errors
        )

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a stick reachable through a serial-to-TCP bridge."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            # pybecker resolves "host:port" to socket://host:port itself
            device = f"{host}:{port}"
            await self.async_set_unique_id(f"socket://{device}")
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(_test_connection, device)
            except BeckerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Becker ({device})",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
                        CONF_DEVICE: device,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_FILENAME: user_input.get(
                            CONF_FILENAME, DEFAULT_DB_FILENAME
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): TextSelector(),
                vol.Required(CONF_PORT, default=DEFAULT_TCP_PORT): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=65535, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Coerce(int),
                ),
            }
        )
        schema = schema.extend(
            {
                vol.Optional(
                    CONF_FILENAME, default=DEFAULT_DB_FILENAME
                ): TextSelector()
            }
        )
        return self.async_show_form(
            step_id=CONNECTION_TYPE_NETWORK, data_schema=schema, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure how Home Assistant connects to the Centronic stick."""
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_serial", "reconfigure_network"],
        )

    async def async_step_reconfigure_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry to use a serial connection."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            device = user_input[CONF_DEVICE]
            try:
                await self.hass.async_add_executor_job(_test_connection, device)
            except BeckerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_and_abort(
                    entry,
                    data_updates={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                        CONF_DEVICE: device,
                        CONF_FILENAME: user_input.get(
                            CONF_FILENAME,
                            entry.data.get(CONF_FILENAME, DEFAULT_DB_FILENAME),
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE,
                    default=entry.data.get(CONF_DEVICE, DEFAULT_DEVICE),
                ): SerialPortSelector(),
                vol.Optional(
                    CONF_FILENAME,
                    default=entry.data.get(CONF_FILENAME, DEFAULT_DB_FILENAME),
                ): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="reconfigure_serial",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure an existing entry to use a network connection."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            device = f"{host}:{port}"
            try:
                await self.hass.async_add_executor_job(_test_connection, device)
            except BeckerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_and_abort(
                    entry,
                    data_updates={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
                        CONF_DEVICE: device,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_FILENAME: user_input.get(
                            CONF_FILENAME,
                            entry.data.get(CONF_FILENAME, DEFAULT_DB_FILENAME),
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=entry.data.get(CONF_HOST, ""),
                ): TextSelector(),
                vol.Required(
                    CONF_PORT,
                    default=entry.data.get(CONF_PORT, DEFAULT_TCP_PORT),
                ): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=65535, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Coerce(int),
                ),
                vol.Optional(
                    CONF_FILENAME,
                    default=entry.data.get(CONF_FILENAME, DEFAULT_DB_FILENAME),
                ): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="reconfigure_network",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the YAML cover platform configuration."""
        async_create_issue(
            self.hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            breaks_in_ha_version="2026.12.0",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={
                "domain": DOMAIN,
                "integration_title": "Becker",
            },
        )

        device = import_data.get(CONF_DEVICE) or DEFAULT_DEVICE
        # Mirror pybecker's device detection to derive the connection type
        if "/" in device or device.upper().startswith("COM"):
            connection_type = CONNECTION_TYPE_SERIAL
            unique_id = device
            data: dict[str, Any] = {
                CONF_CONNECTION_TYPE: connection_type,
                CONF_DEVICE: device,
            }
        else:
            connection_type = CONNECTION_TYPE_NETWORK
            host, _, port = device.partition(":")
            port_number = int(port) if port else DEFAULT_TCP_PORT
            device = f"{host}:{port_number}"
            unique_id = f"socket://{device}"
            data = {
                CONF_CONNECTION_TYPE: connection_type,
                CONF_DEVICE: device,
                CONF_HOST: host,
                CONF_PORT: port_number,
            }
        data[CONF_FILENAME] = import_data.get(CONF_FILENAME) or DEFAULT_DB_FILENAME

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Connection is intentionally not tested here: if the stick is
        # offline during a restart, entry setup retries via
        # ConfigEntryNotReady instead of dropping the YAML covers.
        subentries = []
        for slug, cover_config in import_data[CONF_COVERS].items():
            cover_data = _import_cover_data(slug, cover_config)
            subentries.append(
                {
                    "subentry_type": SUBENTRY_TYPE_COVER,
                    "data": cover_data,
                    "title": cover_data[CONF_FRIENDLY_NAME],
                    "unique_id": cover_data[CONF_CHANNEL],
                }
            )

        return self.async_create_entry(
            title="Becker", data=data, subentries=subentries
        )


class CoverSubentryFlowHandler(ConfigSubentryFlow):
    """Handle adding and reconfiguring covers."""

    def __init__(self) -> None:
        """Init the cover subentry flow."""
        self._cover_input: dict[str, Any] = {}
        self._reuse_confirmed: tuple[int, int] | None = None
        self._learn_task: asyncio.Task[tuple[str, list[str]] | None] | None = None
        self._learned_remote = ""
        self._heard_buttons: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new cover."""
        errors: dict[str, str] = {}
        current = [
            subentry.data[CONF_CHANNEL]
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_COVER
        ]
        known = await async_known_channels(self.hass, self._get_entry().entry_id)
        current_keys = {_channel_key(channel) for channel in current}
        removed_keys = {_channel_key(channel) for channel in known} - current_keys

        if user_input is not None:
            errors = _validate_cover_input(user_input, require_channel=True)
            channel = user_input[CONF_CHANNEL]
            if not errors:
                key = _channel_key(channel)
                if key in current_keys:
                    errors[CONF_CHANNEL] = "already_configured"
                elif key in removed_keys and self._reuse_confirmed != key:
                    # A removed cover's motor may still listen on this channel.
                    # Warn once; submitting the same channel again keeps it.
                    self._reuse_confirmed = key
                    errors[CONF_CHANNEL] = "channel_used_before"
            if not errors:
                self._cover_input = user_input
                return await self.async_step_pair()

        suggested = user_input
        if suggested is None:
            # Prefer channels no cover ever used; only fall back to channels
            # of removed covers when the stick has no unused channel left.
            free = _next_free_channel(current + known) or _next_free_channel(current)
            suggested = {CONF_CHANNEL: free} if free else None
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                COVER_ADD_SCHEMA, suggested
            ),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Optionally pair the receiver before creating the cover."""
        channel = self._cover_input[CONF_CHANNEL]

        if user_input is not None:
            entry = self._get_entry()
            if user_input[CONF_PAIR] and entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.pair(channel)
            return self.async_create_entry(
                title=self._cover_input.get(CONF_FRIENDLY_NAME)
                or f"Channel {channel}",
                data=self._cover_input,
                unique_id=channel,
            )

        return self.async_show_form(
            step_id="pair",
            data_schema=PAIR_SCHEMA,
            description_placeholders={CONF_CHANNEL: channel},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an existing cover. The channel is immutable."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}

        if user_input is not None:
            settings = dict(user_input)
            learn_remote = settings.pop(CONF_LEARN_REMOTE, False)
            errors = _validate_cover_input(settings, require_channel=False)
            if (
                not errors
                and learn_remote
                and self._get_entry().state is not ConfigEntryState.LOADED
            ):
                errors["base"] = "not_loaded"
            if not errors:
                if learn_remote:
                    self._cover_input = settings
                    return await self.async_step_learn_remote()
                return self._async_save_reconfigure(settings)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                COVER_RECONFIGURE_SCHEMA, user_input or subentry.data
            ),
            description_placeholders={CONF_CHANNEL: subentry.data[CONF_CHANNEL]},
            errors=errors,
        )

    @callback
    def _async_save_reconfigure(self, settings: dict[str, Any]) -> SubentryFlowResult:
        """Store the reconfigured cover settings and finish the flow."""
        subentry = self._get_reconfigure_subentry()
        return self.async_update_and_abort(
            self._get_entry(),
            subentry,
            title=settings.get(CONF_FRIENDLY_NAME) or subentry.title,
            data_updates={**settings, CONF_CHANNEL: subentry.data[CONF_CHANNEL]},
        )

    async def async_step_learn_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Listen for presses on a physical Becker remote.

        Only listens: nothing is sent, so the integration moves no cover.
        """
        if self._learn_task is None:
            self._learn_task = self.hass.async_create_task(
                self._async_wait_for_remote()
            )
        if not self._learn_task.done():
            return self.async_show_progress(
                step_id="learn_remote",
                progress_action="learn_remote",
                progress_task=self._learn_task,
                description_placeholders={"seconds": str(LEARN_REMOTE_TIMEOUT)},
            )
        heard = self._learn_task.result()
        self._learn_task = None
        if heard is None:
            return self.async_show_progress_done(next_step_id="learn_remote_failed")
        self._learned_remote, self._heard_buttons = heard
        if self._learned_remote in _remote_ids(self._cover_input.get(CONF_REMOTE_ID)):
            return self.async_show_progress_done(next_step_id="learn_remote_known")
        if self._covers_linked_to(self._learned_remote):
            return self.async_show_progress_done(
                next_step_id="learn_remote_confirm_linked"
            )
        return self.async_show_progress_done(next_step_id="learn_remote_confirm")

    async def _async_wait_for_remote(self) -> tuple[str, list[str]] | None:
        """Wait until one remote was pressed twice.

        Returns its id (unit:channel) and the buttons heard, or None on timeout.
        """
        heard: asyncio.Future[tuple[str, list[str]]] = self.hass.loop.create_future()
        counter = _PressCounter()

        @callback
        def _packet_received(packet) -> None:
            if heard.done():
                return
            channel = packet.group("channel").decode().upper()
            # "F" is the all-channels button of a multi-channel remote;
            # wait for presses on the cover's own channel instead.
            if channel == "F":
                return
            remote_id = f"{packet.group('unit_id').decode().upper()}:{channel}"
            button = decode_event_type(packet.group("command"), packet.group("argument"))
            presses = counter.add(remote_id, button, time.monotonic())
            if len(presses) >= LEARN_REMOTE_PRESSES:
                heard.set_result((remote_id, list(presses)))

        unsubscribe = async_dispatcher_connect(
            self.hass, signal_for_entry(self._get_entry().entry_id), _packet_received
        )
        try:
            async with asyncio.timeout(LEARN_REMOTE_TIMEOUT):
                return await heard
        except TimeoutError:
            return None
        finally:
            unsubscribe()

    def _covers_linked_to(self, remote_id: str) -> list[str]:
        """Return the names of the other covers already following this remote."""
        own_id = self._get_reconfigure_subentry().subentry_id
        return [
            subentry.title
            for subentry in self._get_entry().subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_COVER
            and subentry.subentry_id != own_id
            and remote_id in _remote_ids(subentry.data.get(CONF_REMOTE_ID))
        ]

    def _heard_placeholders(self) -> dict[str, str]:
        """Describe what was heard in terms the user recognises."""
        unit_id, _, channel = self._learned_remote.partition(":")
        return {
            "buttons": ", ".join(self._heard_buttons),
            "remote_id": unit_id,
            "remote_channel": channel,
            "covers": ", ".join(self._covers_linked_to(self._learned_remote)),
        }

    async def async_step_learn_remote_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show what was heard and let the user link it or try again."""
        return self.async_show_menu(
            step_id="learn_remote_confirm",
            menu_options=["learn_remote_link", "learn_remote", "save_without_remote"],
            description_placeholders=self._heard_placeholders(),
        )

    async def async_step_learn_remote_confirm_linked(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Like confirm, but warn that other covers already follow this remote."""
        return self.async_show_menu(
            step_id="learn_remote_confirm_linked",
            menu_options=["learn_remote_link", "learn_remote", "save_without_remote"],
            description_placeholders=self._heard_placeholders(),
        )

    async def async_step_learn_remote_known(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The remote heard is already linked to this cover."""
        return self.async_show_menu(
            step_id="learn_remote_known",
            menu_options=["save_without_remote", "learn_remote"],
            description_placeholders=self._heard_placeholders(),
        )

    async def async_step_learn_remote_link(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add the remote that was heard to the cover and save."""
        self._cover_input[CONF_REMOTE_ID] = _add_remote_id(
            self._cover_input.get(CONF_REMOTE_ID), self._learned_remote
        )
        return self._async_save_reconfigure(self._cover_input)

    async def async_step_learn_remote_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Offer to listen again or save the other settings without a remote."""
        return self.async_show_menu(
            step_id="learn_remote_failed",
            menu_options=["learn_remote", "save_without_remote"],
            description_placeholders={"seconds": str(LEARN_REMOTE_TIMEOUT)},
        )

    async def async_step_save_without_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Save the other settings without learning a remote."""
        return self._async_save_reconfigure(self._cover_input)


@asynccontextmanager
async def _entry_operation_lock(entry: ConfigEntry):
    """Serialize database maintenance with live Becker commands."""
    becker = entry.runtime_data if entry.state is ConfigEntryState.LOADED else None
    if becker is None or not hasattr(becker, "operation_lock"):
        yield None
        return
    async with becker.operation_lock:
        yield becker


class BeckerOptionsFlow(OptionsFlow):
    """Import and export the shutter database from the UI."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the import/export menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "communication_settings",
                "export_json",
                "import_json",
                "export_db",
                "import_db",
            ],
        )

    async def async_step_communication_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure RF command queue and retry behavior."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_QUEUE_SIZE,
                    default=self.config_entry.options.get(
                        CONF_QUEUE_SIZE, DEFAULT_QUEUE_SIZE
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=1000)),
                vol.Required(
                    CONF_COMMAND_RETRY_MAX,
                    default=self.config_entry.options.get(
                        CONF_COMMAND_RETRY_MAX, DEFAULT_COMMAND_RETRY_MAX
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                vol.Required(
                    CONF_COMMAND_RETRY_DELAY,
                    default=self.config_entry.options.get(
                        CONF_COMMAND_RETRY_DELAY, DEFAULT_COMMAND_RETRY_DELAY
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=10.0)),
            }
        )
        return self.async_show_form(
            step_id="communication_settings", data_schema=schema
        )

    def _download_url(self, fmt: str) -> str:
        """Build a short-lived signed download URL for the given format."""
        path = DOWNLOAD_URL.format(entry_id=self.config_entry.entry_id, fmt=fmt)
        return async_sign_path(
            self.hass, path, timedelta(minutes=DOWNLOAD_LINK_TTL_MINUTES)
        )

    async def _db_path(self) -> str:
        """Resolve the database file path for this entry."""
        from . import _resolve_db_path

        return await self.hass.async_add_executor_job(
            _resolve_db_path,
            self.hass.config.config_dir,
            self.config_entry.data.get(CONF_FILENAME),
        )

    async def async_step_export_json(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the JSON state as a download link and inline copy."""
        if user_input is not None:
            return self.async_abort(reason="export_done")

        from .db_transfer import dump_state_json, read_units

        db_path = await self._db_path()
        units = await self.hass.async_add_executor_job(read_units, db_path)
        inline = dump_state_json(units, dt_util.now().isoformat())
        return self.async_show_form(
            step_id="export_json",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_STATE_TEXT, default=inline): TextSelector(
                        TextSelectorConfig(
                            multiline=True, type=TextSelectorType.TEXT
                        )
                    )
                }
            ),
            description_placeholders={"download_url": self._download_url("json")},
        )

    async def async_step_export_db(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the raw .db file as a download link."""
        if user_input is not None:
            return self.async_abort(reason="export_done")
        return self.async_show_form(
            step_id="export_db",
            data_schema=vol.Schema({}),
            description_placeholders={"download_url": self._download_url("db")},
        )

    def _backup_path(self, suffix: str) -> str:
        """Return a timestamped backup file path in the config directory."""
        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
        return self.hass.config.path(f"{BACKUP_PREFIX}{stamp}{suffix}")

    async def async_step_import_json(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Upload and apply a JSON state export."""
        from .db_transfer import (
            StateFormatError,
            StateJSONError,
            StateRollbackError,
            apply_units,
            dump_state_json,
            ensure_no_rollback,
            parse_state_json,
            read_units,
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            with process_uploaded_file(self.hass, user_input[CONF_UPLOAD]) as path:
                raw = await self.hass.async_add_executor_job(path.read_bytes)
            try:
                rows = parse_state_json(raw)
            except StateJSONError:
                errors["base"] = "invalid_json"
            except StateFormatError:
                errors["base"] = "invalid_format"
            if not errors:
                db_path = await self._db_path()
                async with _entry_operation_lock(self.config_entry):
                    current = await self.hass.async_add_executor_job(
                        read_units, db_path
                    )
                    try:
                        ensure_no_rollback(current, rows)
                    except StateRollbackError:
                        errors["base"] = "rollback_detected"
                    if not errors:
                        backup = self._backup_path(".json")
                        await self.hass.async_add_executor_job(
                            _write_text,
                            backup,
                            dump_state_json(current, dt_util.now().isoformat()),
                        )
                        await self.hass.async_add_executor_job(
                            apply_units, db_path, rows
                        )
                if errors:
                    return self.async_show_form(
                        step_id="import_json",
                        data_schema=vol.Schema(
                            {
                                vol.Required(CONF_UPLOAD): FileSelector(
                                    FileSelectorConfig(
                                        accept=".json,application/json"
                                    )
                                )
                            }
                        ),
                        errors=errors,
                    )
                return self.async_abort(reason="import_done")

        return self.async_show_form(
            step_id="import_json",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPLOAD): FileSelector(
                        FileSelectorConfig(accept=".json,application/json")
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_import_db(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Upload and swap in a raw .db file."""
        from .db_transfer import (
            StateRollbackError,
            ensure_no_rollback,
            is_valid_becker_db,
            read_units,
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            with process_uploaded_file(self.hass, user_input[CONF_UPLOAD]) as path:
                valid = await self.hass.async_add_executor_job(
                    is_valid_becker_db, path
                )
                if not valid:
                    errors["base"] = "invalid_db"
                else:
                    db_path = Path(await self._db_path())
                    incoming = await self.hass.async_add_executor_job(
                        read_units, str(path)
                    )
                    async with _entry_operation_lock(self.config_entry) as becker:
                        current = await self.hass.async_add_executor_job(
                            read_units, str(db_path)
                        )
                        try:
                            ensure_no_rollback(current, incoming)
                        except StateRollbackError:
                            errors["base"] = "rollback_detected"
                        if not errors:
                            backup = Path(self._backup_path(".db"))
                            if becker is None:
                                await self.hass.async_add_executor_job(
                                    _swap_db, db_path, path, backup
                                )
                            else:
                                await self.hass.async_add_executor_job(
                                    _swap_live_db,
                                    becker,
                                    db_path,
                                    path,
                                    backup,
                                )
            if not errors:
                self.hass.config_entries.async_schedule_reload(
                    self.config_entry.entry_id
                )
                return self.async_abort(reason="import_done")

        return self.async_show_form(
            step_id="import_db",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPLOAD): FileSelector(
                        FileSelectorConfig(accept=".db,application/octet-stream")
                    )
                }
            ),
            errors=errors,
        )


def _write_text(path: str, text: str) -> None:
    """Write text to a file (blocking, run in executor)."""
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def _swap_live_db(becker, db_path: Path, uploaded: Path, backup: Path) -> None:
    """Atomically replace a live database and reopen the runtime connection."""
    from .db_transfer import consistent_copy
    from .pybecker.database import Database

    consistent_copy(db_path, backup)
    tmp = db_path.with_name(db_path.name + ".new")
    shutil.copy2(uploaded, tmp)
    os.replace(tmp, db_path)

    old_db = becker.db
    old_db.close()
    try:
        becker.db = Database(str(db_path))
    except Exception:
        restore = db_path.with_name(db_path.name + ".restore")
        shutil.copy2(backup, restore)
        os.replace(restore, db_path)
        becker.db = Database(str(db_path))
        raise


def _swap_db(db_path: Path, uploaded: Path, backup: Path) -> None:
    """Back up the live db consistently, then atomically swap in the upload.

    consistent_copy uses sqlite's backup API so the backup is a clean snapshot
    even though the entry's Becker still holds an open connection; os.replace
    swaps atomically so the live connection keeps its old inode until reload.
    """
    from .db_transfer import consistent_copy

    if db_path.exists():
        consistent_copy(db_path, backup)
    tmp = db_path.with_name(db_path.name + ".new")
    shutil.copy2(uploaded, tmp)
    os.replace(tmp, db_path)
