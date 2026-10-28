# Changelog

## [1.0.4](https://github.com/Gyang91/hass-becker-component-plus-pybecker/compare/v1.0.3...v1.0.4) (2026-10-28)


### Code Refactoring

* share availability handling in a BeckerStickEntity base class ([dc742b6](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/dc742b657892a8daf9a5b54a80fc15430fae7ded))

## [1.0.3](https://github.com/Gyang91/hass-becker-component-plus-pybecker/compare/v1.0.2...v1.0.3) (2026-10-28)


### Bug Fixes

* **pybecker:** send RELEASE after each button command ([227ff6c](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/227ff6cea4d3dab9a93e658888fb2182232b4ca8))

## [1.0.2](https://github.com/Gyang91/hass-becker-component-plus-pybecker/compare/v1.0.1...v1.0.2) (2026-10-28)


### Documentation

* credit only the original authors in README ([89deefc](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/89deefc945fc45d1a05e5419182db69c8b4c3c1d))

## [1.0.1](https://github.com/Gyang91/hass-becker-component-plus-pybecker/compare/v1.0.0...v1.0.1) (2026-10-28)


### Documentation

* fix README badges, add HACS install button and credits ([ad0b299](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/ad0b299eb8432a46447033dd15009dce5c47dce3))

## [1.0.0](https://github.com/Gyang91/hass-becker-component-plus-pybecker/compare/v0.7.1...v1.0.0) (2026-10-27)


### Bug Fixes

* **cover:** cancel a pending partial-move stop when a new movement starts ([4363e75](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/4363e75fe7f9bb4987d9c9edd41e9fd706ac8592))
* declare file_upload dependency and platform-only config schema ([bab1019](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/bab1019d27faa31614a9e69e4dfc71554ca28cc8))
* **pybecker:** bound the receive buffer to a possible partial frame ([61e04f8](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/61e04f87b3f05e0dffbba61d5618498d1e31b7a1))
* **pybecker:** persist rolling-code counter before queueing packets ([f71db00](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/f71db00c7c66da3a3fa2c8d199a6da23262691c5))
* release the stick when setup fails and report real unit ids ([a39af0a](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/a39af0a011a5724d65de2ef955496bc588b13a57))


### Continuous Integration

* automate releases with release-please and add Dependabot ([f2866bf](https://github.com/Gyang91/hass-becker-component-plus-pybecker/commit/f2866bf8246048686f50509d4acc4f9ce0b51f6d))

## 0.6.1

A connectivity visibility and availability refresh release.

- Add a diagnostic connectivity binary sensor on the Centronic stick device
- Update the connectivity sensor immediately when the communicator goes offline or recovers
- Refresh cover, pair-button and remote-event availability immediately on connection changes
- Log one warning when the Becker connection becomes unavailable and one info message when it is restored
- Keep repeated low-level reconnect attempts at debug level to avoid warning-log spam
- Keep queue, retry and RF packet details in diagnostics instead of adding noisy entities

## 0.6.0

A Home Assistant UX and resilience milestone.

### Highlights

- Add config-entry reconfiguration for switching or updating serial and network connections
- Validate replacement connections before saving and reload the existing entry in place
- Preserve existing config-entry identity while changing connection details
- Add actionable Home Assistant Repair issues for unavailable connections and invalid database paths
- Automatically clear setup Repair issues after a successful setup
- Mark cover, pair-button and remote-event entities unavailable when the communicator cannot currently accept RF work
- Keep RF command generation, rolling-code handling and database state semantics unchanged

## 0.5.3

A diagnostics hardening release.

- Keep Home Assistant diagnostics downloadable when database inspection fails
- Keep diagnostics downloadable when communicator status inspection fails
- Report only exception types for failed diagnostics sections, not sensitive exception text
- Mark database and communication diagnostic sections explicitly as available or unavailable

## 0.5.2

A diagnostics and supportability release.

- Add native Home Assistant config-entry diagnostics
- Report privacy-safe connection, thread, RF queue and retry status
- Report configured cover/channel and database-unit counts without exposing rolling codes
- Keep device addresses, database paths, remote IDs and rolling-code state out of diagnostics
- Let Home Assistant fully control logging configuration

## 0.5.1

A small logging and diagnostics polish release.

- Use configured cover names in movement debug logs instead of Home Assistant's entity-name placeholder
- Make movement start/stop messages shorter and easier to scan
- Remove per-second Home Assistant state-refresh callback noise while preserving live position updates
- Keep RF communication and meaningful movement diagnostics available at debug level

## 0.5.0

A modernization and reliability milestone for the maintained Becker Home Assistant integration.

### Highlights

- Modern Home Assistant UI configuration with config entries and cover subentries
- Serial USB and serial-to-TCP connection setup
- In-UI pairing and re-pairing
- Remote-control button presses exposed as event entities
- Rolling-code-safe JSON and SQLite export/import with automatic backups
- Protection against stale rolling-code imports and configured-state rollback
- Serialized imports, RF commands and SQLite access
- Resilient USB/network reconnect behavior
- Strict setup-time connection validation
- RF queue backpressure and retry handling
- Blocking RF queue writes moved off Home Assistant's asyncio event loop
- Live cover position tracking improvements
- Automated CI and regression test coverage against current Home Assistant releases
- Explicit service targeting for installations with multiple Becker config entries
- Safer database-path validation
- Refreshed project documentation and branding

### Compatibility

The integration remains compatible with existing centronic-stick.db state. Because Becker uses rolling codes, always keep a current state backup before migrating or restoring an installation.

## 0.4.x

The 0.4.x series introduced the initial maintained-fork modernization work that is consolidated in 0.5.0, including UI configuration, database import/export, reconnect hardening, rolling-code protection, SQLite serialization and event-loop hardening.
