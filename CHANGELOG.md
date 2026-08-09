# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `auditlogger/collector/router/` provider package: `RouterProvider` abstract interface, `RouterConnection` connection parameters, `RouterClient` shared HTTP session handling, and `AutoDetectionProvider` (current default, not yet implemented).
- Added a router orchestrator (`collect_router_info`) that selects a provider from `config["router"]["detection"]["type"]` and delegates collection to it.
- Added an optional `network.router` field to audit events, populated only when the router collector returns data.
- Added regression tests for the router orchestrator and for the config loader's nested-section parsing.
- Added `tests/test_signature.py` (offline RSA/AES chunking-and-hash math checker), `tests/live_login_test.py` (live end-to-end login smoke test), and `tests/live_status_test.py` (live end-to-end status-field smoke test) against a real router. All three are manual/opt-in - they need real captured or live credentials filled in and are not part of the automated suite - kept for diagnosing future firmware or protocol changes. See the module docstring in each for usage.
- Added `ConfigError` (`config/loader.py`), raised for a missing config file, invalid YAML, or a config missing a section `main.py` depends on (`storage.log_file`, `telegram`, `router`). Validated eagerly, once, right after loading - previously a missing section could pass silently until the first run that actually touched it (e.g. `telegram` was only ever subscripted once a notifiable change occurred), surfacing as a raw `KeyError` deep inside `run_once()`.
- Added a top-level `try/except ConfigError` in `main.py`'s CLI entry point: configuration problems now exit with a one-line message on stderr and exit code 1, not a full traceback.
- Added `tests/test_capabilities.py` and `tests/test_notification_triggers.py`, covering `detect_capabilities()` and `_detect_notifiable_changes()` respectively.
- Added firmware version/model/hardware version, WAN uptime, and aggregate connected-client count to `TplinkProvider.collect()`'s return value, via new `get_firmware()` and `get_status()` calls made in the same authorized session as the existing `get_ipv4_status()` call.
- Added an opt-in `router.include_device_list` config flag. When true, `TplinkProvider.collect()` also returns a `devices` list (hostname, MAC, IP, connection type, active) for every client currently connected to the router. Defaults to false - unlike every other field this provider collects, a per-device list identifies specific devices on the network, not just the router's own state.

### Fixed

- Fixed TP-Link login always failing with 403 on the Archer AX72: `TplinkProvider` depended entirely on upstream `tplinkrouterc6u`'s auto-detection, whose client classes all assume RSA-PKCS1v1.5 signing. The AX72's firmware actually signs login requests with nested RSA-OAEP chunking (53-char outer split, then a further OAEP-max-size inner split - see `tplink_ax72.py` for the full derivation and confirmed protocol details), which no upstream class implements. Added `TplinkRouterAX72`, tried first via a real `authorize()` attempt in `TplinkProvider`, falling back to upstream auto-detection for any other TP-Link router. Confirmed against a real device with `tests/live_login_test.py` (successful `stok` + `sysauth` session, twice, with two different credential sets) and `tests/live_status_test.py` (confirmed real WAN IP/gateway/DNS returned correctly through the full `authorize() -> get_ipv4_status() -> logout()` flow).

### Changed

- Changed the fallback YAML parser in `config/loader.py` to support arbitrary nesting depth, required by the new `router.connection.*` config fields.
- Renamed `collect_network_info`'s parameter from `config` to `router_config` for clarity (it only ever received the router section).
- Changed the default notification trigger from `external_ip_change` to `wan_change`: the router's WAN interface reconnects, renews its DHCP lease, or re-authenticates far more often than the public IP itself changes, so `wan_change` is now the only `notify_on` trigger enabled by default. `external_ip_change` is still supported but now opt-in.
- Added `conn_type_change`, `wan_mac_change`, and `dns_change` as opt-in `notify_on` triggers, backed by new fields (`conn_type`, `wan_mac`) added to `TplinkProvider.collect()`'s return value alongside the existing `wan_ip`, `gateway`, `dns_primary`, and `dns_secondary`.
- Declared `pycryptodome` as a direct dependency in `pyproject.toml`. `tplink_ax72.py` imports it directly (`Crypto.Cipher`, `Crypto.PublicKey.RSA`); it was previously only present transitively via `tplinkrouterc6u`, which isn't a guarantee upstream will keep it that way.
- Changed `config/loader.py` to raise `ConfigError` instead of a bare `FileNotFoundError` for a missing config file, for consistency with the other config-loading failure modes.
- Changed `TplinkProvider`'s collection-failure log message to include a one-line hint (likely cause: wrong credentials or an unreachable admin panel) alongside the raw underlying error, instead of only the raw error text - the underlying error text alone (e.g. `tplinkrouterc6u`'s JSON-parse error on an empty response) isn't actionable without already knowing what usually causes it.
- Fixed `scheduler/tasks.py`'s startup task: the scheduled action now runs via `cmd.exe /c cd /d "<project_root>" && ...` instead of invoking python directly. Task Scheduler's default "start in" folder for a bare executable target is the executable's own directory, not this project - relative paths like `storage.log_file` in `config.example.yaml` would otherwise resolve against the wrong working directory on a real logon-triggered run.
- Fixed `scheduler/tasks.py`'s trigger scope: `/SC ONLOGON` without `/RU <user>` fires on *any* user's logon to the machine, not just the one installing it. Now sets `/RU` to the current user explicitly.

### Security

- No change - router credentials remain part of the gitignored local config, same as the Telegram token.

### Known Limitations

- `AutoDetectionProvider` is a stub and returns no data yet; WAN/DNS/gateway collection is still pending (Phase 2 of `docs/refactoring-roadmap.md`).

## [1.0.0] - 2026-06-25

### Added

- Added the initial Windows-focused AuditLogger application.
- Added manual execution through `python -m auditlogger.main`.
- Added Windows Task Scheduler helper for running AuditLogger at user logon.
- Added external IP collection with fallback endpoints.
- Added local IP detection based on the outbound route selected by Windows.
- Added adapter-specific MAC address collection using the adapter section associated with the selected local IP.
- Added adapter name collection.
- Added hostname, platform, and boot time collection.
- Added UTC timestamps and local timestamps with timezone offsets.
- Added JSONL audit log storage.
- Added SHA256 event hashing and previous-hash linking.
- Added Telegram notification support for external IP changes.
- Added local configuration loading from `auditlogger/config/config.yaml`.
- Added a small fallback YAML parser for the bundled config shape.
- Added unit tests for event shape, local timestamp offset, and adapter parsing.
- Added maintenance-oriented module, class, and function docstrings.

### Security

- Ignored local logs, local config, Python caches, and local agent metadata.
- Kept Telegram tokens and chat IDs out of version control by ignoring `auditlogger/config/config.yaml`.

### Known Limitations

- AuditLogger currently runs once per manual execution or user logon.
- It is not a continuous background service.
- Full chain-wide integrity verification is planned for a later version.
- Email notifications and daily archives are placeholders for future work.