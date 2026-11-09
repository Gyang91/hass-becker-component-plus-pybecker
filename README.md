[![release](https://img.shields.io/github/v/release/Gyang91/hass-becker-component-plus-pybecker?label=release&color=blue)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![CI](https://img.shields.io/github/actions/workflow/status/Gyang91/hass-becker-component-plus-pybecker/ci.yml?branch=main&label=CI)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/actions/workflows/ci.yml)
[![HACS validation](https://img.shields.io/github/actions/workflow/status/Gyang91/hass-becker-component-plus-pybecker/validate.yml?branch=main&label=HACS%20validation)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/actions/workflows/validate.yml)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-brightgreen?logo=dependabot)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/blob/main/.github/dependabot.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Gyang91/hass-becker-component-plus-pybecker/blob/main/LICENSE)

<p align="center"><img src="https://raw.githubusercontent.com/Gyang91/hass-becker-component-plus-pybecker/main/brand/logo.png" alt="Becker for Home Assistant" width="512"></p>

# Becker for Home Assistant

Home Assistant integration for **Becker Centronic RF covers** (roller shutters, blinds, sun protection, compatible Roto roof windows) through a Becker Centronic USB stick.

Fork of [RainerStaude/hass-becker-component-plus-pybecker](https://github.com/RainerStaude/hass-becker-component-plus-pybecker) (originally by [ole](https://github.com/ole1986) and [Nicolas Berthel](https://github.com/nicolasberthel)). The bundled `pybecker/` is based on pybecker 1.1.0 and keeps its RF frame and rolling-code format. Changes: [CHANGELOG.md](CHANGELOG.md).

> **Rolling codes:** keep a current state export before migrating Home Assistant or restoring a backup. Imports that would move a rolling-code counter backwards are rejected.

## Features

- UI setup for a local USB stick or a serial-to-TCP bridge (e.g. ser2net)
- Covers as config subentries, paired from Home Assistant
- Open, close, stop, set position, tilt / intermediate positions
- Position estimated from travel time, a template, or physical remote presses
- Link a physical remote by pressing STOP twice
- Remote button presses as event entity and bus event
- Rolling-code-safe JSON and SQLite import/export
- Automatic reconnect; serialized RF commands and database access
- Diagnostics, repair issues, reconfiguration

## Supported hardware

| Item | Supported |
|---|---|
| USB stick | Becker Centronic, order numbers **4035 200 041 0** and **4035 000 041 0** |
| Connection | local USB/serial, or a transparent serial-to-TCP bridge (`socket://host:port`) |
| Receivers | Becker Centronic roller shutters, blinds and sun protection; Roto roof windows with Becker RF remotes |

## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Gyang91&repository=hass-becker-component-plus-pybecker&category=integration)

Or: HACS → ⋮ → Custom repositories → `https://github.com/Gyang91/hass-becker-component-plus-pybecker`, type **Integration** → download **Becker Centronic** → restart Home Assistant.

### Manual

Copy the integration files to `/config/custom_components/becker/` and restart Home Assistant.

## Setup

1. **Settings → Devices & services → Add integration → Becker.**
2. Connection type:
   - **Serial port (USB stick)**: select the stick's serial port.
   - **Network (serial-to-TCP bridge)**: host and port (default `5000`).
3. **Add cover** for each cover (see [Cover settings](#cover-settings)). Leave **Send pairing signal now** ticked to pair it straight away (see [Pair a cover](#pair-a-cover)).

An existing YAML configuration is imported on the next restart; then remove it from `configuration.yaml` (a repair issue reminds you). See [Legacy YAML](#legacy-yaml-deprecated).

## Entities

| Entity | Per | Description |
|---|---|---|
| Cover | cover | Open / close / stop / position / tilt. Reports an *assumed state*: open, close and stop stay available even at the end positions, because the position is an estimate. |
| **Pair** button | cover | Sends the pairing signal for this cover's channel. |
| **Remote** event | stick | Fires for every packet the stick receives from a physical Becker remote, including remotes not linked to a cover. |
| **Connection** binary sensor | stick | Live availability of the stick (diagnostic). |

## Cover settings

**Settings → Devices & services → Becker → Add cover**, or **⋮ → Reconfigure** on an existing cover. Positions use Home Assistant's scale: `0` closed, `100` open.

| Setting | Meaning | Default |
|---|---|---|
| Channel | Stick channel `1`–`7`, or `unit:channel` (unit `1`–`5`). Only when adding. | next free channel |
| Name | Cover name | — |
| Travel time up | Seconds from fully closed to fully open | — |
| Travel time down | Seconds from fully open to fully closed | same as up |
| Remote ID(s) | Physical remotes that move this cover, `ID:channel`, comma-separated | — |
| Position template | Template that overwrites the position (see below) | — |
| Enable intermediate positions | Motor has the two intermediate positions programmed | on |
| Intermediate position up | Position reached by double-tapping ▲ | `25` |
| Intermediate position down | Position reached by double-tapping ▼ | `75` |
| Tilt moves to intermediate position | Tilt open/close drive to the intermediate positions | on while intermediate positions are enabled and venetian blind is off |
| Tilt as venetian blind | Tilt open/close send a short movement (slats) instead | off |
| Blind tilt time | Length of that short movement, seconds | `0.3` |
| Learn a remote now | Reconfigure only: start [Learn a remote](#learn-a-remote) | off |

### Pair a cover

The stick acts as an additional remote. Keep your existing remote as the master; don't program the stick as master.

1. Put the receiver into pairing mode (usually: hold the programming button on the master remote until the motor clicks once; see your Becker manual).
2. New cover: in **Add cover** keep the suggested **Channel**, submit, leave **Send pairing signal now** ticked. Existing cover: press its **Pair** button.
3. The receiver confirms with a single click followed by a double click.

### Position by travel time

Enter **Travel time up** (and optionally **Travel time down**). With a travel time set, the cover accepts a target position (`cover.set_cover_position`). Not available when a **Position template** is set.

### Position template

Re-evaluated on every change of its result:

| Result | Effect |
|---|---|
| number `0`–`100` | sets that position |
| `open`, `true` | open |
| `closed`, `false` | closed |
| `unknown`, `unavailable`, `none` | position unchanged |

Example: confirm only "closed", keep the travel-time estimate otherwise:

```jinja
{{ 0 if is_state('binary_sensor.roof_window', 'off') else None }}
```

### Intermediate positions

Program the two positions on the motor first (Becker manual), then enter where they are:

- **Up:** time from fully closed to the ▲▲ position ÷ **Travel time up** × 100. Example: 9 s ÷ 30 s × 100 = `30`.
- **Down:** 100 − (time from fully open to the ▼▼ position ÷ **Travel time down** × 100). Example: 100 − 18 s ÷ 26 s × 100 ≈ `31`.

No positions programmed: untick **Enable intermediate positions**.

## Learn a remote

Links a physical remote to a cover, so its presses update the cover's position.

1. Cover → **Reconfigure** → tick **Learn a remote now** → submit.
2. Within **45 seconds**, press **STOP ■ twice**, about 2 s apart, on the remote you use for this cover (switch a multi-channel remote to this cover first). No STOP button: press ▲ twice (the cover moves).
3. Home Assistant shows the presses it heard. Choose **Link this remote**, **Listen again**, or **Save settings without linking**.

Two presses from the same remote are required, so a stray press is never linked. Learning only listens; nothing is sent. Manual alternative: enter `ID:channel` in **Remote ID(s)** (ID from the **Remote** event entity or the debug log).

## Remote events

| Source | Data |
|---|---|
| **Remote** event entity | event type `up`, `up_intermediate`, `down`, `down_intermediate`, `halt`, `release`, `unknown`; attributes `unit_id`, `channel`, `command_code` |
| Bus event `becker_remote_packet_received` | `unit`, `channel`, `command` |

Example automation:

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

## Actions

| Action | Fields | Description |
|---|---|---|
| `becker.pair` | `channel` (1–7), `unit` (1–5, optional), `entry_id` (only with several sticks) | Pairing signal; same as the **Pair** button. |
| `becker.log_units` | `entry_id` (only with several sticks) | Logs every configured unit with its unit code and rolling-code increment. |

```yaml
action: becker.pair
data:
  channel: 1
  unit: 1
```

## Options

**Settings → Devices & services → Becker → Configure.**

### Communication

| Setting | Default |
|---|---|
| Command queue size | `100` |
| Queue retry attempts | `3` |
| Delay between retries | `1.0` s |

The stick reconnects automatically after a transient USB or network failure; a command already taken from the queue is retried after reconnect.

### State import / export

The rolling-code counters live in `centronic-stick.db` in the Home Assistant config folder, not on the stick. Swapping only the stick keeps the pairings.

| Menu entry | Effect |
|---|---|
| Export state (JSON) | Download `becker_state.json` (increment and paired flag per unit) |
| Import state (JSON) | Back up current state to `becker_db_backup_<timestamp>.json`, then apply |
| Export database file | Download an exact copy of `centronic-stick.db` |
| Import database file | Back up to `becker_db_backup_<timestamp>.db`, replace the file, reload |

Imports are rejected if they would move a counter backwards or mark a configured unit as unconfigured. Export right before moving, and don't operate covers from the old install afterwards.

## Units and channels

- The stick emulates up to **5 remotes (units)** with unit codes `1737b`–`1737f`; unit `1` is the default.
- Each unit addresses up to **7 channels**; channel `15` is a broadcast to all receivers.
- `1` and `1:1` are the same channel. A channel can hold only one cover.

## Limitations

- No position feedback from Becker receivers: position is estimated (travel time) unless a position template is set.
- Rolling-code counters live in Home Assistant; restoring older state can desynchronize a receiver.
- No automatic USB discovery; the serial port is chosen during setup.
- Pairing needs the receiver in learn mode (master remote).
- A network connection needs a transparent serial-to-TCP bridge, which the integration does not manage.
- Removing a cover doesn't unpair its motor (do that with the master remote). **Add cover** never suggests a channel a removed cover used and warns if you enter one. Covers removed before 1.3.1 aren't remembered.
- Two sticks can't both have a cover on the same channel; the second cover is not created.

## Troubleshooting

- Restart Home Assistant after plugging in the stick.
- **Connection** sensor on the stick device shows whether the stick is reachable.
- Debug log: **Settings → Devices & services → Becker → ⋮ → Enable debug logging**, reproduce, then **Disable debug logging** to download the log. Each received remote press logs a line like `Received packet: unit_id: 12345, channel: 2, command: HALT, …`.
- Diagnostics for bug reports: **⋮ → Download diagnostics**.
- Help: [Home Assistant Community thread](https://community.home-assistant.io/t/integrating-becker-motors-in-to-hassio/151705) or [GitHub issues](https://github.com/Gyang91/hass-becker-component-plus-pybecker/issues).

Permanent debug logging:

```yaml
logger:
  logs:
    custom_components.becker: debug
```

## Removal

**Settings → Devices & services → Becker → ⋮ → Delete.** This does not unpair receivers from the stick. Export the state first if you may need the rolling-code state again.

## Legacy YAML (deprecated)

Read once and imported into the UI; remove it afterwards. Options match the UI fields.

```yaml
cover:
  - platform: becker
    device: "/dev/serial/by-id/usb-BECKER-ANTRIEBE_GmbH_CDC_RS232_v125_Centronic-if00"  # optional; or socket://192.168.1.20:5000
    filename: "centronic-stick.db"  # optional, in the config folder
    covers:
      living_room:
        friendly_name: "Living room"
        channel: "2:1"                  # "1"-"7" or "unit:channel"
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
