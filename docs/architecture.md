# Project Architecture

## Purpose

This document describes the high-level architecture of the project, the responsibility of each module, and the design principles that should guide future development.

It is intentionally focused on architecture rather than implementation details. For "what's here and how to run it," see the root README - this document only covers *why* things are shaped the way they are, and the rules new code should follow to stay consistent. If you're adding a directory or renaming a module, update README's layout tree; if you're adding or changing a design rule, it belongs here.

---

# Design Goals

The project should remain:

- Simple
- Predictable
- Easy to extend
- Easy to test
- Platform-focused (Windows-first)
- Safe for forensic and audit scenarios

New functionality should be added with minimal impact on existing components.

---

# Core Principles

## Single Responsibility

Each module should have one clear responsibility.

Examples:

- collecting information
- writing logs
- sending notifications
- loading configuration

Modules should not perform unrelated tasks.

---

## Separation of Concerns

Collecting data, storing data, and reacting to changes are separate responsibilities.

Example:

A network collector should never send Telegram notifications.

A notification provider should never collect network information.

---

## Extensibility

The project should support adding new data sources and notification backends without modifying existing components whenever possible.

Future additions should primarily consist of new modules rather than changes to existing ones.

---

## Predictable Behaviour

One execution of the application should produce one consistent audit snapshot.

Providers should avoid repeated collection of the same information unless explicitly required.

Collectors should fail independently. A failure in one collector must not prevent the application from producing a valid snapshot using the remaining collectors.

---

## Fail Loud, Not Silent

A collector that fails independently (previous principle) must still be observable - it should never fail *invisibly*. Every caught exception that results in a fallback value (`None`, `{}`, `False`, etc.) must be logged before the fallback is returned, at a level matching its severity:

- `warning` - a single attempt failed but the collector may still succeed via another path, or the failure only affects one optional field.
- `error` - every fallback for a field was exhausted; that field will be null/empty in this run's event.
- `debug` - failures with no practical consequence (e.g. a best-effort cleanup call failing).

Logging must never change what's returned - only what's recorded about the failure. See `auditlogger/logging_config.py` for how output destinations (console, file) and level are configured.

---

# High-Level Architecture

    Application

    ├── Configuration
    ├── Data Sources
    ├── Storage
    ├── Notifications
    ├── Logging
    └── Scheduler

---

# Components

## Configuration

Responsibilities:

- load configuration
- validate configuration
- expose configuration to the application

Configuration should not contain business logic.

Configuration errors are a setup problem for the person running the tool, not a bug - they should be reported as a short, specific message (what's missing, where to fix it) and the process should exit cleanly, never with a raw traceback. `auditlogger/config/loader.py`'s `ConfigError` is the single type used for this: a missing config file, invalid YAML, and a config missing a section the application depends on all raise it, and it's validated once, eagerly, right after loading - not discovered piecemeal wherever a section happens to first get subscripted. `main.py`'s CLI entry point is the only place that catches it.

---

## Data Sources

Responsible for collecting information from the operating system, network, or external systems.

Examples:

- Public IPv4
- Public IPv6
- Router WAN
- Local interfaces
- System information

Every data source should expose a consistent interface.

Example:

collect()

returns

- collected value(s)
- metadata
- collection timestamp

Data sources should never:

- write logs
- send notifications
- modify configuration

---

## Storage

Responsible for persistent storage.

Examples:

- JSONL logs
- archive creation
- hash chain
- integrity verification

Storage modules should never collect information directly.

---

## Notifications

Responsible for informing the user about important events.

Examples:

- Telegram
- Email
- Future providers

Notification modules receive events.

They never decide whether an event occurred.

---

## Logging

Responsible for recording what happened during a run - separate from the audit event JSONL, which records what was *observed*. Logging captures execution diagnostics (failures, fallbacks, timing), never the audited data itself.

- One central configuration point (`auditlogger/logging_config.py`) driven by `config["logging"]`; individual modules only call `logging.getLogger(__name__)` and log - they never configure handlers themselves.
- Logging is diagnostic, not a source of truth. The JSONL hash chain remains the only tamper-evident record; logs may be rotated, truncated, or disabled without affecting audit integrity.

---

## Scheduler

Responsible only for deciding when the application executes.

Scheduling logic should remain independent from business logic.

---

# Future Provider Architecture

The project should evolve toward a provider-based architecture.

Example:

    Data Source

    ├── Public IP
    ├── Router WAN
    ├── IPv6
    └── Future Sources

Each provider should be self-contained.

Adding a new provider should require creating a new module instead of modifying unrelated code.

---

# Router Integrations

Router-specific implementations should remain isolated under their own package, one level below the network collector that consumes them:

    auditlogger/collector/router/

    base.py       # RouterProvider - abstract interface every provider implements
    connection.py # RouterConnection - connection/credential parameters
    client.py      # RouterClient - shared HTTP session handling (requests-based)
    detection.py  # AutoDetectionProvider - fallback default, returns {} (not yet implemented)
    tplink.py     # TplinkProvider - wraps tplinkrouterc6u's own auto-detection (get_client());
                  #   no vendor/firmware-variant special-casing lives here - see CHANGELOG for why an earlier bespoke AX72 override was added,
                  #   then removed once upstream covered it
    __init__.py   # collect_router_info() - orchestrator; selects a provider from
                  #   config["router"]["detection"]["type"] and delegates to it
    mikrotik.py   # future vendor providers follow the same RouterProvider interface
    asus.py
    keenetic.py

The application should communicate only with the common interface (`RouterProvider.collect()`), reached only through the orchestrator (`collect_router_info()`).

It should not contain vendor-specific logic outside the individual provider modules. Where a vendor already has a well-tested open-source client library (as TP-Link does), prefer wrapping that library over reimplementing the vendor's login/API protocol from scratch - see `tplink.py`'s module docstring for the reasoning.

---

# Configuration Philosophy

The application should automatically discover as much information as reasonably possible.

Users should only provide information that cannot be discovered automatically.

Examples:

✓ Telegram token

✓ Router credentials

✓ Optional router address

Examples of information that should preferably be discovered automatically:

- local interfaces
- gateway
- router address
- public IP
- available capabilities

---

# Capability Detection

Whenever practical, the application should detect supported features automatically.

Example:

Detected capabilities:

✓ Public IP lookup

✓ Router detected

✓ Router vendor identified

✓ WAN IP supported

Capability detection should improve usability while remaining optional. It is diagnostic output for the person running the tool (printed after a run), not part of the persisted/hashed audit event - it summarizes the event, it doesn't become audited fact itself.

---

# Testing Philosophy

Every new feature should be testable independently.

Data sources should be testable without notification modules.

Notification modules should be testable without storage.

---

# Documentation

- Code (docstrings, inline comments) explains *how* a specific implementation works.
- This document explains *why* the project is shaped the way it is, and the rules new code should follow.
- README explains *what* exists and how to run it.

When something changes, update the one of these three that actually answers "why did that change," not all three by default.

---

# Long-Term Vision

The project should grow by adding new providers instead of increasing complexity inside existing modules.

The preferred direction is:

small independent modules

over

large centralized logic.