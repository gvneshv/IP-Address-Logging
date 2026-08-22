# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `MikrotikProvider` (`collector/router/mikrotik.py`), a second router provider alongside TP-Link, backed by the RouterOS API via `librouteros` rather than HTTP. Unlike TP-Link hardware, RouterOS has no fixed WAN port, so which interface counts as WAN can't be auto-detected - it's now a required `router.wan_interface` config field, enforced by `ConfigError` if missing. Confirmed against a real RouterOS 6.45.9 device (RB951Ui-2nD): `system/resource`/`system/routerboard` identity fields, the `ip/address`/`interface` WAN-IP/MAC lookup (including a RouterOS quirk where an address configured on a bridge port reports via both `interface` and `actual-interface` - this provider correctly matches on `interface`), and the "no default route, no dhcp-client" branch, which correctly returns `None` for `conn_type`/`gateway`/`dns_primary`/`dns_secondary` rather than a guessed value (the test device turned out to be running in pure bridge/switch mode, not routing). The `conn_type: "dhcp"` branch is implemented but **not yet verified against a live DHCP-client WAN** - flagged in the module docstring pending a device that actually exercises it. `wan_uptime_seconds` is intentionally always `None` for MikroTik: RouterOS doesn't expose a WAN-specific "time since connected" counter the way `tplinkrouterc6u` does. Added `librouteros>=4.1.1` to `pyproject.toml`, documented the new `router.wan_interface`/`detection.type: mikrotik` config shape in `config.example.yaml` and `README.md`, and added 5 orchestration tests to `tests/test_router.py` mirroring the existing TP-Link coverage (suite verified passing, 38/38).
- **Upstream PR #193 merged** into `AlexandrErohin/TP-Link-Archer-C6U:main` - the AX72 login fix (`TplinkRouterAX72`, `test_client_ax72.py`, provider registration) originally built in this project is now part of upstream `tplinkrouterc6u`. Confirmed against real hardware post-merge: `TplinkRouterProvider.get_client()` -> `authorize()` -> `get_ipv4_status()`/`get_status()`/`get_firmware()` -> `logout()` all succeed. Surprising, and worth recording accurately: `get_client()` actually returns `TplinkRouterSG` for this project's real AX72, not `TplinkRouterAX72` - the device apparently carries `SG CLS L1 STAGE2`/`EU CE RED` certification, and `TplinkRouterSG`'s certification-based auto-detection recognizes it independently of the AX72-specific merge. See "Removed," below.
- Added `README.md` documentation clarifying that Telegram's `chat_id` is the chat the bot posts *into* (for a private DM with your own bot, your own numeric Telegram user ID), not the bot's own ID - a real point of confusion during setup this session (a 404 from a malformed `getUpdates` URL, then genuine ambiguity about whose ID `chat_id` actually refers to). No code change; `TelegramNotifier` was already correct, just under-documented.
- Added a real `EmailNotifier` (`notifications/email.py`), replacing the `send_email_placeholder` stub that had returned `False` unconditionally since 1.0.0. SMTP-based, defaults to STARTTLS on port 587 (`smtp_use_ssl: true` switches to implicit TLS, typically port 465). Fails closed (logs a warning, returns `False`, never raises) on a misconfigured-but-enabled notifier or a connection/auth failure - matches how `TelegramNotifier` and the router collectors already fail. `run_once()` now sends to both Telegram and email (independently enabled/disabled) on the same triggers. Added `tests/test_email.py` (6 tests, `smtplib` fully mocked - no real SMTP connection is ever attempted). **Confirmed working end-to-end** - a real config change triggered a real received email.
- Added `email` to `config/loader.py`'s required config sections, alongside `storage`, `telegram`, and `router`.

### Removed

- Removed the local `TplinkRouterAX72` workaround (`collector/router/tplink_ax72.py`) and the "try AX72 first, fall back to auto-detection" special-casing in `TplinkProvider`. `TplinkProvider.collect()` now calls plain `TplinkRouterProvider.get_client()` with no vendor/firmware-variant knowledge of its own. This wasn't just "now redundant since upstream has our fix" - confirmed via live testing that upstream's `TplinkRouterSG` already covered this project's exact device *before* the AX72-specific merge even factored in (see "Added," above), so the local workaround provided no coverage this device didn't already have once `tplinkrouterc6u` was current. The original fix (nested RSA-OAEP chunking, SHA-256 hashing, no `&confirm=true`) remains a real, documented piece of work - see the `[Unreleased]`/`[1.0.0]` history above for the full derivation - it's just no longer needed *in this project*, having graduated into (a slightly different form of) the upstream library itself.
- Removed `tests/test_signature.py`, `tests/live_login_test.py`, and `tests/live_status_test.py` - all three tested the now-removed local `TplinkRouterAX72` implementation directly and have no remaining purpose. `TplinkProvider.collect()`'s standard operation (exercised every real run of `python -m auditlogger.main`) is now the live verification, rather than a separate bespoke script.
- Bumped `tplinkrouterc6u` from `>=5.21.0` to `>=5.29.0` in `pyproject.toml` (the version confirmed, via live testing, to authenticate against this project's router). Removed `pycryptodome` as a direct dependency - it was added when `tplink_ax72.py` imported `Crypto.Cipher`/`Crypto.PublicKey.RSA` directly; with that file gone, it's back to being purely a transitive dependency of `tplinkrouterc6u`, same as before that addition.
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
- Fixed TP-Link router collection failing for 4 consecutive days with `Cannot authorize! Error - Expecting value: line 1 column 1 (char 0)`, despite no config changes and manual browser login working throughout. Root cause: `poetry.lock` was stale at `tplinkrouterc6u==5.27.0`, even though `pyproject.toml` already required `>=5.29.0` - on 5.27.0, `TplinkRouterProvider.get_client()` misdetects this project's real Archer AX72 as the generic `TplinkRouter` class instead of `TplinkRouterSG`, and the generic class's `form=login` request is rejected outright (`403`, empty body) by the router's current firmware. Confirmed via a debug script exercising the exact `authorize()`/`logout()` flow with `urllib3` DEBUG logging enabled: `TplinkRouter` on 5.27.0 gets two consecutive `403`s on `form=login`; after `poetry lock` picked up `5.31.0`, detection correctly lands on `TplinkRouterSG` and `form=login` returns `200` with a valid `stok`/`sysauth` session. Fixed by running `poetry lock` to bring the lock file in line with the constraint already declared in `pyproject.toml` - no code changes needed, since `TplinkProvider.collect()` already delegates model selection entirely to `get_client()`.
- Fixed router collection failing immediately after the above fix with `Timeout value connect was 30, but it must be an int, float or None.` Root cause: PyYAML was never declared as a project dependency in `pyproject.toml`, despite `config/loader.py`'s `load_config()` importing it directly and relying on it for correct scalar parsing - it had only ever been present incidentally in the environment. The `poetry lock`/`poetry install` run above correctly rebuilt the venv from the lock file alone, which had no reason to include an undeclared package, and PyYAML's absence silently switched config loading to the bundled fallback parser (`_load_simple_yaml`/`_parse_scalar`). That fallback only special-cases `true`/`false`, `[]`, and quoted strings - a bare `router.connection.timeout: 30` falls through unconverted and is returned as the string `"30"` rather than an int. `urllib3`'s timeout validation (`Timeout._validate_timeout`) doesn't actually use its own `float(value)` type-check result; it then compares the *original* value against `0`, and comparing a `str` to an `int` raises a `TypeError` that gets reported as the misleading "must be an int, float or None" message even though the value is entirely numeric-looking. Confirmed via a debug script printing the config value's type at each stage (raw config -> `RouterConnection.timeout`) before and after the fix. Fixed by adding `pyyaml` as an explicit dependency via `poetry add pyyaml`, restoring correct integer parsing.


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
- Confirmed the startup task end-to-end on a real machine: creation requires an elevated (Administrator) terminal (explicit `/RU` needs admin rights on Windows, even for the current user - a non-elevated attempt fails with `ERROR: Access is denied.`), and after that, a real logon-triggered run correctly creates `logs/` under the project root rather than under the Python install directory. README updated with the elevation requirement.

### Security

- No change - router credentials remain part of the gitignored local config, same as the Telegram token.

### Known Limitations

- `AutoDetectionProvider` is a stub and returns no data yet; WAN/DNS/gateway collection is still pending (Phase 2 of `docs/refactoring-roadmap.md`).
- `MikrotikProvider`'s `conn_type: "dhcp"` branch (gateway/DNS read from an active `ip/dhcp-client` lease) is implemented but unverified against real hardware - the only test device available runs a static bridge configuration, not a DHCP-assigned WAN. Re-verify before relying on it for a DHCP-based MikroTik WAN.
- Router providers beyond TP-Link and MikroTik (Asus, Ubiquiti, generic SNMP, etc.) remain unimplemented - see `CONTRIBUTING.md` if you have hardware to test one against.
- `config/loader.py`'s fallback YAML parser (used only when PyYAML is unavailable) does not parse bare numeric scalars - a value like `30` is returned as the string `"30"` rather than an int. This was the proximate trigger for the timeout bug above and remains unfixed in the parser itself; PyYAML now being a declared dependency makes the fallback path unlikely to be hit in this project going forward, but the parser would still misbehave the same way for any downstream user running without PyYAML installed. Worth hardening in a future pass if the fallback parser is meant to be a genuine safety net rather than YAML-shaped documentation.

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