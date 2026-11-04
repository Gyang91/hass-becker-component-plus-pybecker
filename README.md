[![release](https://img.shields.io/github/v/release/Gyang91/hass-becker-component-plus-pybecker?label=release&color=blue)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![CI](https://img.shields.io/github/actions/workflow/status/Gyang91/hass-becker-component-plus-pybecker/ci.yml?branch=main&label=CI)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/actions/workflows/ci.yml)
[![HACS validation](https://img.shields.io/github/actions/workflow/status/Gyang91/hass-becker-component-plus-pybecker/validate.yml?branch=main&label=HACS%20validation)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/actions/workflows/validate.yml)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-brightgreen?logo=dependabot)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/blob/main/.github/dependabot.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/blob/main/LICENSE)
[![commits](https://img.shields.io/github/commit-activity/y/Gyang91/hass-becker-component-plus-pybecker?label=commits)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commits/main)

# Becker for Home Assistant

_Originally created by [ole](https://github.com/ole1986) and [Nicolas Berthel](https://github.com/nicolasberthel), continued by [Rainer Staude](https://github.com/RainerStaude/hass-becker-component-plus-pybecker); this fork by [Gyang91](https://github.com/Gyang91) brings it to current Home Assistant releases. See [Highlights](#highlights)._

<p align="center"><img src="https://raw.githubusercontent.com/Gyang91/hass-becker-component-plus-pybecker/main/brand/logo.png" alt="Becker for Home Assistant" width="512"></p>

A maintained Home Assistant integration for controlling **Becker Centronic RF covers** with a Becker Centronic USB stick.

This fork focuses on current Home Assistant releases, UI-first configuration, reliable RF communication and safe handling of Becker rolling-code state. It supports Becker roller shutters, blinds and sun protection as well as compatible Roto roof windows using RF remotes.

Supported Centronic USB stick order numbers include **4035 200 041 0** and **4035 000 041 0**.

## Highlights

- UI setup for local USB and serial-to-TCP connections
- Cover subentries with pairing directly from Home Assistant
- Open, close, stop, position and tilt/intermediate controls
- Position tracking by travel time, template or physical remote commands
- Remote button presses exposed as Home Assistant event entities
- Link a physical remote to a cover by pressing STOP twice ([Learn a remote](#learn-a-remote))
- Open and close always available in the dashboard, because the position is an estimate
- Rolling-code-safe JSON and SQLite backup/import tools
- Automatic reconnect after transient USB or network failures
- Serialized database access and RF command handling
- Configurable RF queue/retry behavior
- Automated regression tests against current Home Assistant releases
- Native diagnostics, repair issues and UI reconfiguration
- Diagnostic connectivity sensor with live availability updates

> **Important:** Becker uses rolling codes. Keep a current backup of the integration state before migrating Home Assistant or restoring a database. The integration rejects imports that would move known rolling-code state backwards.

The project builds on the original work by [ole](https://github.com/ole1986), [Nicolas Berthel](https://github.com/nicolasberthel), [Rainer Staude](https://github.com/RainerStaude/hass-becker-component-plus-pybecker) and later contributors. Version 1.0.0 is the first release of this repository.

The bundled `pybecker/` code is based on Nicolas Berthel's **pybecker 1.1.0** and is maintained as an embedded fork for this Home Assistant integration. The original Centronic RF frame generation and rolling-code format are retained, while this fork adds Home Assistant-specific reliability improvements such as asynchronous command handling, serialized database access, reconnect and retry behavior, runtime availability reporting, diagnostics, and safe state import/export.


## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Gyang91&repository=hass-becker-component-plus-pybecker&category=integration)

Or manually:

1. In HACS, open **⋮ → Custom repositories**, add `https://github.com/Gyang91/hass-becker-component-plus-pybecker` with type **Integration**.
2. Install **Becker Centronic**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for **Becker**.

### Manual installation

Copy the integration files to `/config/custom_components/becker/`, restart Home Assistant, then add **Becker** from **Settings → Devices & services**.

## Supported hardware

The integration is designed for Becker Centronic RF installations controlled through a Becker Centronic USB stick.

Known USB stick order numbers:

- **4035 200 041 0**
- **4035 000 041 0**

Supported end devices include Becker Centronic roller shutters, blinds and sun-protection receivers that can be paired with the USB stick. Compatible Roto roof-window installations using Becker RF remotes are also known to work.

The integration can connect to the stick either locally over USB/serial or over a serial-to-TCP bridge such as ser2net.

## How state is updated

Becker Centronic is primarily a one-way RF system: the cover normally does not report its physical position back to Home Assistant.

Home Assistant therefore updates cover state from one or more of these sources:

- commands sent by Home Assistant;
- configured travel times, which are used to estimate position while a cover moves;
- received commands from configured physical Becker remotes;
- an optional position template backed by another Home Assistant entity.

Because the position is an estimate, covers report an *assumed state*: open, close and stop stay available in the dashboard even when Home Assistant thinks the cover is already fully open or closed, so you can always correct a wrong estimate.

The **Connection** diagnostic binary sensor reflects live communicator availability. Received physical-remote packets are also exposed through the **Remote** event entity and the `becker_remote_packet_received` event.

## Example use cases

Typical uses include:

- controlling existing Becker shutters and blinds from Home Assistant without replacing the motors or receivers;
- keeping Home Assistant position estimates in sync when wall or hand-held Becker remotes are used;
- using a roof-window or rain sensor as an external source for position state;
- reacting to Becker remote button presses in Home Assistant automations;
- connecting the USB stick through a serial-to-TCP bridge when Home Assistant is hosted away from the stick.

### Automation example: react to a Becker remote

The integration fires `becker_remote_packet_received` whenever it receives a supported remote packet. The following example reacts to the UP button of a specific remote/channel:

```yaml
automation:
  - alias: "Becker remote - hallway light"
    triggers:
      - trigger: event
        event_type: becker_remote_packet_received
        event_data:
          unit: "12345"
          channel: "2"
          command: "up"
    actions:
      - action: light.toggle
        target:
          entity_id: light.hallway
```

To find a remote's ID and channel, use **Learn a remote** (below), the **Remote** event entity or debug logging.

## Learn a remote

Physical Becker remotes talk to the cover directly, so Home Assistant only knows the cover moved if it hears that remote. To link a remote to a cover:

1. Open **Settings → Devices & services → Becker**, find the cover and choose **Reconfigure**.
2. Tick **Learn a remote now** and submit.
3. Within 45 seconds, press **STOP ■ twice** on the remote, about 2 seconds apart.
   - STOP is the button with the square symbol **■**. On most Becker hand-held remotes it sits between ▲ and ▼, but look for the symbol rather than the position. STOP doesn't start the cover moving.
   - **Remote with several channels?** First select the channel you normally use on that remote to move this cover: the one where ▲ moves this cover. This is the remote's own channel and has nothing to do with the **Channel** number you entered in Home Assistant (that one belongs to the USB stick). Don't use the setting that moves all covers at once; it is ignored.
   - Remote with a single channel: nothing to select.
   - If your remote has no STOP button, press ▲ twice instead, about 2 seconds apart. The cover will move.
4. Home Assistant shows what it heard, for example **■ STOP, ■ STOP from remote 1737B, remote channel 2**. You don't need to know the ID: check that the buttons match what you just pressed. Then choose:
   - **Link this remote** to add it. From then on, presses on that remote update the cover's position in Home Assistant.
   - **Listen again** if the buttons don't match, for example because someone else used a remote at the same time.
   - **Save settings without linking** to keep your other changes only.

Two presses from the same remote are needed, so a single stray press from another remote is never picked up. If the remote is already linked to another cover, Home Assistant names that cover. That's fine when one remote channel controls several covers. If the remote is already linked to this cover, nothing is added.

Learning only listens: the integration sends nothing while it waits. If no remote is heard, you can listen again or save your other changes without a remote.

## Known limitations

- Becker Centronic covers do not provide native position feedback. Position control is estimated from travel time unless an external position template is configured.
- RF commands use rolling-code counters stored in Home Assistant. Restoring an older database or state export can desynchronize a receiver, so rollback protection is deliberately enforced.
- Automatic USB discovery is not currently implemented; the serial device is selected during setup.
- Pairing still requires the target Becker receiver to be placed into its learn/pairing mode.
- Network connections require a transparent serial-to-TCP bridge; the integration does not configure or manage that bridge.
- Legacy YAML configuration is supported for migration but is deprecated in favor of UI configuration.
- Two Centronic sticks in one Home Assistant can't both have a cover on the same channel: the second cover is not created. Use different channels or units on the second stick.

## Removal

To remove the integration, go to **Settings → Devices & services → Becker**, open the integration menu and choose **Delete**.

Removing the Home Assistant config entry does not unpair the physical Becker receiver from the Centronic USB stick. If you also want to change the receiver's paired transmitters, follow the Becker receiver/remote instructions before deleting your Home Assistant state.

Before deleting or migrating an installation, export the Becker state or database if you may need the rolling-code state again later.

## Configuration via the UI (recommended)
Since version 0.4.0 the integration is set up in the Home Assistant UI:

1. Go to **Settings** → **Devices & services** → **Add integration** and search for **Becker**.
2. Choose the connection type:
   - **Serial port (USB stick)**: select the serial port of the Centronic USB stick.
   - **Network (serial-to-TCP bridge)**: enter host and port of your bridge (for example ser2net, default port 5000).
3. Add your covers to the created entry with **Add cover**. Each cover can be
   reconfigured later (name, travel times, tilt, remote IDs, position template)
   without removing it. See [Cover settings: how-to guides](#cover-settings-how-to-guides)
   for what each setting does.
4. While adding a cover you can pair it straight away: put the shutter receiver
   into learn mode, then leave **Send pairing signal now** enabled. You can also
   pair (or re-pair) any time later with the **Pair** button on the cover's
   device page - no need for the `becker.pair` service.

An existing YAML configuration (see [Legacy YAML reference](#legacy-yaml-reference-deprecated)) is imported automatically on the
next restart. After the import, remove the `becker` cover platform from your
`configuration.yaml` - a repair issue will remind you. YAML configuration is
deprecated and will be removed in a future release.

## Remote presses as events

The integration exposes a **Remote** event entity per stick (on the Centronic
stick device). Every RF packet the stick receives from a physical Becker remote
fires an event on it: the button is the event type (`up`, `down`, `halt`,
`release`, the two intermediate variants, or `unknown`), and the sending
remote's `unit_id` and `channel` are event attributes.

Use it as an automation trigger — trigger on the entity and filter by
`unit_id`/`channel` to react to a specific wall remote — or just watch it to see
which remotes the stick is hearing (handy for discovering a remote's id). It
works for any remote in range, including ones not configured as covers.

## Communication settings

Open **Settings → Devices & Services → Becker → Configure → Communication** to tune the RF command queue and retry behavior.

The defaults are intended for normal installations. Increasing the queue size can help when many commands are issued in a short burst. Retry count and delay control how temporary queue saturation is handled.

The communicator also survives transient USB disconnects. When the USB stick reappears, the serial connection is rebuilt automatically. A command that was already dequeued when a transient write failure occurs is kept pending and retried after reconnect instead of being silently dropped.

## Import / Export the shutter database

The stick's rolling-code counters live in a SQLite database **on the Home
Assistant host** (`centronic-stick.db` in your config folder), not on the USB
stick itself — so swapping only the physical stick already keeps your pairings.
Import/export is for moving that state between Home Assistant installs, taking
backups, or repairing a desynced increment.

Open **Settings → Devices & Services → Becker → Configure**:

- **Export state (JSON)** — download a small, human-readable `becker_state.json`
  (the increment counter and paired flag for each unit), or copy it from the box.
- **Import state (JSON)** — upload a `becker_state.json`. The current state is
  backed up to `becker_db_backup_<timestamp>.json` first, then applied.
- **Export database file** — download an exact copy of `centronic-stick.db`.
- **Import database file** — upload a `centronic-stick.db`. The current file is
  backed up to `becker_db_backup_<timestamp>.db`, then swapped in and the
  integration reloads.

> Because Becker uses a rolling code, the imported increment must be at or ahead
> of what each receiver last saw. Export right before moving, and don't keep
> operating covers from the old install afterwards. Since version 0.4.2, imports
> that would move a stored rolling-code counter backwards (or mark an already
> configured unit as unconfigured) are rejected automatically. Since version
> 0.4.3, imports are also serialized with live RF commands so a cover command
> cannot update a rolling-code counter while an import is being applied.
> Since version 0.4.4, access to each live SQLite connection is also serialized
> across Home Assistant's event loop and executor threads.
> Since version 0.4.5, the setup flow performs a strict connection check while
> runtime connections retain automatic reconnect behavior.
> Since version 0.4.6, potentially blocking RF queue writes are offloaded from
> Home Assistant's asyncio event loop while preserving command order.

## Cover settings: how-to guides

All settings below are in the cover's form: **Settings → Devices & services → Becker**, then **Add cover** for a new cover, or **⋮ → Reconfigure** next to an existing cover. Changes take effect right after saving. Positions use Home Assistant's scale: `0` is closed and `100` is open.

### Pair a cover with the USB stick

The stick behaves like an additional Becker remote, so pairing works the same way as adding a second remote to a receiver. Keep your existing remote as the master remote. Don't program the stick as master.

1. Put the receiver into pairing mode. Usually you hold the programming button on the master remote until the motor clicks once. Check your Becker manual for your model.
2. Then do one of these:
   - **New cover:** in **Add cover**, enter the channel and submit. On the next screen, leave **Send pairing signal now** ticked and submit.
   - **Existing cover:** open the cover's device page and press the **Pair** button.
3. The receiver confirms with a single click followed by a double click.

The `becker.pair` action (**Developer tools → Actions**) does the same for advanced use:

```yaml
action: becker.pair
data:
  channel: 1   # 1-7
  unit: 1      # 1-5, optional
```

### Track the position by travel time

Becker covers don't report their position, so Home Assistant estimates it from how long the cover moves.

1. Time the cover from fully closed to fully open, in seconds. Enter it as **Travel time up**.
2. Optional: time it from fully open to fully closed and enter it as **Travel time down**. If you leave it empty, the up time is used for both directions.

With a travel time set, you can also move the cover to a position, for example 40 %, from the dashboard or with `cover.set_cover_position`. This isn't available when the cover uses a **Position template**.

### Follow your physical remotes

Without this, Home Assistant doesn't know when someone uses a Becker remote, and its position estimate drifts.

- **Recommended:** link the remote with [Learn a remote](#learn-a-remote) (press STOP ■ twice).
- **Manually:** enter the ID in **Remote ID(s)** as `ID:channel`, for example `12345:2`. Separate several remotes with commas. You can find an ID on the **Remote** event entity or in the debug log (see [Troubleshooting](#troubleshooting)).

### Set the position from another sensor

For example, a roof window with a rain sensor closes by itself when it rains. Enter a template in **Position template**. Every time the template's result changes, it overwrites the cover's position:

- a number from `0` to `100` sets that position;
- `open`, `true` mean open; `closed`, `false` mean closed;
- `unknown`, `unavailable`, `none` leave the position unchanged.

Use the last group to confirm only one state and keep the travel-time estimate otherwise:

```jinja
{{ 0 if is_state('binary_sensor.roof_window', 'off') else None }}
```

### Intermediate positions

Becker motors can store two intermediate positions: one reached by double-tapping ▲ (from closed) and one reached by double-tapping ▼ (from open). Program them on the motor first, following your Becker manual. Then tell Home Assistant where they are:

- **Intermediate position up:** time the cover from fully closed to the up position (double-tap ▲). Divide by **Travel time up** and multiply by 100. Example: 9 s ÷ 30 s × 100 = `30`.
- **Intermediate position down:** time the cover from fully open to the down position (double-tap ▼). Divide by **Travel time down**, multiply by 100, and subtract the result from 100. Example: 18 s ÷ 26 s × 100 ≈ 69, so `31`.

Defaults are `25` (up) and `75` (down). If your motor has no intermediate positions programmed, untick **Enable intermediate positions**.

### Tilt buttons: intermediate positions or venetian blind

Home Assistant's tilt buttons can do one of two things:

- **Tilt moves to intermediate position** (default when intermediate positions are enabled): tilt open drives to the up position, tilt close to the down position. Untick it if you don't want tilt buttons for this.
- **Tilt as venetian blind:** for Becker venetian blinds, where a short press of ▲/▼ tilts the slats and a long press moves the blind. Tilt open/close sends a short movement. **Blind tilt time** sets how long it is (default 0.3 s); increase it if the slats barely move. This replaces the intermediate tilt.

## Events for Remote Commands
In addition to processing remote commands to update cover states, the
integration also fires explicit events of type
`becker_remote_packet_received` for each command it receives from a remote.
Those events can be used to trigger automations when remote buttons are pressed
or for other custom purposes.

Each event contains data about the remote unit, channel and the command
that has been received, for instance:

```yaml
event_type: becker_remote_packet_received
data:
  unit: "12345"
  channel: "1"
  command: "up"
```

## Units and Channels
The USB stick acts like a remote control
The remote control protocol is able to access up to 7 devices like shutters, these are addressed as "channels" (1-7). There's also a broadcast channel (15) which addresses all of the devices at the same time. With this you are able to send a "UP" or "DOWN" command to all the covers at the same time.

Units are used for devices like shutters. Also, remote controls get an own unit id.
The software is able to "emulate" up to 5 remote controls, named "units".
For these units 1-5, the stick is configured internally to use unit numbers 1737b, 1737c, 1737d, 1737e and 1737f.
You can also see these unit id's in the database.
If you leave out the unit number, the unit number 1 will be used, so the USB stick uses 1737b as a unit id.
This means `1` and `1:1` are the same channel. Home Assistant won't let you add a second cover on a channel that is already used, in either spelling.
I think that's all the magic behind the Becker protocol.

## Troubleshooting
If you have any trouble follow these steps:
- Restart Home Assistant after you have plugged in the USB stick.
- Check the **Connection** sensor on the Centronic stick device: it shows whether the stick is reachable.
- Enable debug logging: **Settings → Devices & services → Becker → ⋮ → Enable debug logging**. Reproduce the problem, then choose **Disable debug logging** to download the log.
- When asking for help, attach the diagnostics file: **Settings → Devices & services → Becker → ⋮ → Download diagnostics**.

Alternatively, enable debug logging permanently in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    # This must correspond to the folder name of your /config/custom_components/becker folder
    custom_components.becker: debug
```

You can also change the log configuration dynamically by calling the `logger.set_level` service. 
This method allows you to enable debug logging only for a limited time:

```yaml
service: logger.set_level
data:
  custom_components.becker: debug
```

All messages are logged to the home-assistant.log file in your config folder.  
It also shows the Remote ID of your Becker Remote (to link a remote to a cover,
[Learn a remote](#learn-a-remote) is easier). The message will be something like
below every time you press a key on your Remote:  
`... DEBUG ... \[custom_components.becker.pybecker.becker_helper]` Received packet: 
unit_id: `12345`, channel: `2`, command: HALT, argument: 0, packet: ...

In case of any errors related to the Becker integration try to fix them.  
If you require additional help have a look at the 
[Home Assistant Community](https://community.home-assistant.io). There is already one thread about the 
Becker integration: 
[Integrating Becker Motors](https://community.home-assistant.io/t/integrating-becker-motors-in-to-hassio/151705)
Another way is to open a new issue on 
[GitHub](https://github.com/Gyang91/hass-becker-component-plus-pybecker/issues).

To disable debug log for becker set the level back from `debug` to `info`.

## Legacy YAML reference (deprecated)

YAML configuration is only read once, to import it into the UI. After that, remove it from `configuration.yaml`; a repair issue reminds you. The options match the UI fields above.

```yaml
cover:
  - platform: becker
    device: "/dev/serial/by-id/usb-BECKER-ANTRIEBE_GmbH_CDC_RS232_v125_Centronic-if00"  # optional
    filename: "centronic-stick.db"  # optional, in the config folder
    covers:
      living_room:
        friendly_name: "Living room"
        channel: "2:1"                  # string: "1"-"7" or "unit:channel"
        travelling_time_up: 30          # Travel time up
        travelling_time_down: 26.5      # Travel time down
        remote_id: "12345:2"            # Remote ID(s)
        value_template: "{{ ... }}"     # Position template
        intermediate_position: on       # Enable intermediate positions
        intermediate_position_up: 25
        intermediate_position_down: 75
        tilt_intermediate: on           # Tilt moves to intermediate position
        tilt_blind: off                 # Tilt as venetian blind
        tilt_time_blind: 0.3            # Blind tilt time
```

The device can also be a `serial_for_url` address such as `socket://192.168.1.20:5000` for a serial-to-TCP bridge.
