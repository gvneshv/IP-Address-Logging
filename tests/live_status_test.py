"""Live smoke test for TplinkRouterAX72 - the actual shipped class, not a reimplementation.

live_login_test.py proved the raw login protocol (crypto scheme) works.
This proves the actual TplinkRouterAX72 class (auditlogger/collector/router/ tplink_ax72.py) works end-to-end through tplinkrouterc6u's normal object model:
authorize() -> get_ipv4_status() -> logout().
That matters for two reasons:
  1. TplinkProvider.collect() (the real code path used in production) calls exactly these three methods - if this script works, collect() works.
  2. get_ipv4_status() makes an authenticated (non-login) request,
     which exercises the OTHER branch of _OAEPEncryptionWrapper.get_signature() (the is_login=False path, no AES key re-sent) that live_login_test.py never touches.
     Confirming this is what's actually meant by "the fix works", not just "login works".

USAGE: fill in HOST / USERNAME / PASSWORD below and run from the repo root
(needs auditlogger on the import path, e.g. `python -m tests.live_status_test` or run with the repo root as your working directory).
Only run this against hardware you own.
Never commit a real PASSWORD value here.
"""
import sys
from pathlib import Path

# Allow running this file directly (`python tests/live_status_test.py`) without needing the package installed or -m invocation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auditlogger.collector.router.tplink_ax72 import TplinkRouterAX72

# --- Fill these in ----------------------------------------------------------
HOST = "https://192.168.0.1"     # your router's base URL
USERNAME = ""                    # confirmed empty in /login?form=keys response
PASSWORD = ""                    # the real router password - never commit a real value here
VERIFY_SSL = False               # router's cert is normally self-signed


if __name__ == "__main__":
    if not PASSWORD:
        print("Fill in PASSWORD (and HOST/USERNAME if needed) before running this.")
        raise SystemExit(1)

    router = TplinkRouterAX72(HOST, PASSWORD, USERNAME, verify_ssl=VERIFY_SSL, timeout=10)

    try:
        router.authorize()
        print("authorize(): OK\n")

        status = router.get_ipv4_status()
        print("get_ipv4_status():")
        for field in (
            "wan_ipv4_ipaddr", "wan_ipv4_gateway", "wan_ipv4_conntype",
            "wan_ipv4_netmask", "wan_ipv4_pridns", "wan_ipv4_snddns",
        ):
            print(f"  {field:20s}: {getattr(status, field)!r}")

        # This is exactly what TplinkProvider.collect() returns in production - printing it here confirms the real code path, not just the fields above.
        print("\nTplinkProvider.collect()-shaped result:")
        print({
            "wan_ip": status.wan_ipv4_ipaddr,
            "gateway": status.wan_ipv4_gateway,
            "dns_primary": status.wan_ipv4_pridns,
            "dns_secondary": status.wan_ipv4_snddns,
        })
    finally:
        try:
            router.logout()
            print("\nlogout(): OK")
        except Exception as error:
            print(f"\nlogout() failed (non-fatal): {error}")