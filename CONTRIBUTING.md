# Contributing

## Adding a new router provider

This project currently supports TP-Link (`tplink.py`, via `tplinkrouterc6u`) and MikroTik
(`mikrotik.py`, via `librouteros`). Both were only merged after being confirmed against real
hardware - not just passing unit tests. This isn't a formality: an untested provider that
*looks* right can be worse than no provider at all, since it fails silently in the field
instead of loudly in review. If you don't have the hardware, please don't write the provider
speculatively - open an issue describing the router instead, so someone who does have it can
pick it up, or come back to it once you do.

### The workflow that produced tplink.py and mikrotik.py

1. **Find the real API/protocol first.** Don't assume a vendor's web admin panel (WebFig,
   the TP-Link login page, etc.) is meant to be scraped - it's usually a heavy JS/Ajax client
   talking to a separate, more stable API or protocol underneath. Look for that instead:
   a documented HTTP API, a binary protocol with a maintained Python client (check PyPI for
   activity - last release date, `requires-python`, open issues), SSH, or SNMP.

2. **Probe before you code.** Write a small throwaway script (not part of the package) that
   connects to the real device and dumps the *raw* output of every call you think you'll need,
   as JSON. Run it against the actual router and look at the real field names and shapes -
   don't guess them from documentation or from memory of a similar library. `mikrotik.py` exists
   because a first attempt at this (`.where(interface=...)`) was wrong about the client
   library's actual method signature, and the probe caught it before it reached any real code.

3. **Write the provider against the real output**, not the probe. Implement
   `RouterProvider` (`collector/router/base.py`):

   ```python
   class RouterProvider(ABC):
       @abstractmethod
       def collect(self) -> dict[str, Any]: ...
   ```

   `collect()` should return whichever of these fields the vendor's API actually exposes -
   omit (don't fabricate) whatever it doesn't:

   | Field | Type | Notes |
   |---|---|---|
   | `wan_ip` | `str \| None` | |
   | `wan_mac` | `str \| None` | |
   | `conn_type` | `str \| None` | e.g. `"static"`, `"dhcp"`, `"pppoe"` |
   | `gateway` | `str \| None` | |
   | `dns_primary` / `dns_secondary` | `str \| None` | |
   | `wan_uptime_seconds` | `int \| None` | Only if the vendor actually exposes a WAN-specific uptime - see `mikrotik.py`'s docstring for why this is `None` there |
   | `firmware_version` / `hardware_version` / `model` | `str \| None` | |
   | `connected_clients_total` | `int \| None` | Always collected when the router is enabled |
   | `devices` | `list[dict] \| omitted` | Only when `router.include_device_list` is `True` - see below |

   Take a `RouterConnection` (`collector/router/connection.py`) in `__init__`, plus whatever
   extra config your vendor genuinely needs (see `mikrotik.py`'s `wan_interface` - required
   because RouterOS has no fixed WAN port to auto-detect, unlike TP-Link hardware). Don't add
   config fields "for flexibility" that nothing reads yet.

   `collect()` must never raise. Wrap the real call in `try/except` for whatever that
   client library actually raises (connection errors, auth errors), log a `warning` with an
   *actionable* hint (likely cause: wrong credentials, unreachable host, the vendor's API
   service being disabled - not just the raw exception text), and return `{}`. Every provider
   fails independently; one bad router shouldn't break the rest of the audit snapshot.

   If a *required config field* is missing (like MikroTik's `wan_interface`), that's different -
   raise `ConfigError` (`config/loader.py`) at provider-construction time in
   `collector/router/__init__.py`'s selector, not a generic exception, and not silently inside
   `collect()`.

   If the device's actual behavior means a field genuinely doesn't apply (e.g. `mikrotik.py`
   returning `None` for `conn_type`/`gateway`/`dns_*` when the interface isn't routing WAN
   traffic at all), say so in a code comment and return `None` - don't guess a plausible-looking
   value to fill the shape.

4. **Wire it into the selector** (`collector/router/__init__.py`'s `match` statement) under
   `detection.type`, and document the new config shape in `config.example.yaml` and `README.md`
   (see the "MikroTik support" section there for the level of detail expected - especially
   any known limitations, called out explicitly rather than left for someone to discover).

5. **Add orchestration tests** to `tests/test_router.py`, mirroring the existing pattern for
   each provider: enabled-config delegates to the provider, provider-specific required fields
   are forwarded to the constructor, `include_device_list` forwarding/default. These mock the
   provider's `collect()` - they test that config correctly reaches your provider, not your
   provider's internal API calls (there's no live credential in the automated suite). Run
   `python -m unittest discover -s tests` and confirm the full suite passes, not just your
   new tests.

6. **Update `CHANGELOG.md`** under `[Unreleased]`/`Added`, including what was actually verified
   against real hardware versus what's implemented-but-unverified (see the MikroTik entry for
   the level of honesty expected - it explicitly calls out the untested DHCP-client branch).

### Commit split

Split changes by theme, roughly matching how TP-Link and MikroTik were done:

1. `feat(router): add <vendor> provider` - the provider file itself
2. `feat(router): wire <vendor> detection type` - the `__init__.py` selector change
3. `chore(deps): add <client-library>` - `pyproject.toml`
4. `docs(config): document <vendor> config fields` - `config.example.yaml`
5. `test(router): add <vendor> orchestration tests` - `tests/test_router.py`
6. `docs(readme): document <vendor> support` - `README.md`

Small, single-theme commits - easier to review, easier to revert one piece if it's wrong.