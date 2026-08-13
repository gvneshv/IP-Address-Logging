"""TP-Link router provider, backed by the third-party tplinkrouterc6u client.

TP-Link's admin-panel login uses a proprietary RSA/AES-encrypted password
exchange that differs across firmware generations. Rather than reimplement
that here, this wraps tplinkrouterc6u (https://github.com/AlexandrErohin/TP-Link-Archer-C6U),
an actively maintained, open-source library that auto-selects the right client class for the detected router model via TplinkRouterProvider.get_client().

History: earlier versions of this provider carried a bespoke TplinkRouterAX72 class
(nested RSA-OAEP signature chunking - see CHANGELOG for the full writeup) to work around a 403 on this project's Archer AX72,
which no upstream class handled at the time.
That fix has since been merged upstream (AlexandrErohin/TP-Link-Archer-C6U#193, not yet in a PyPI release as of tplinkrouterc6u 5.29.0).
It turned out not to be needed here any more anyway:
plain get_client() already authenticates against this project's real AX72 via TplinkRouterSG,
which recognizes it independently of the AX72-specific merge (certification-based auto-detection - confirmed against real hardware:
a real AX72's get_client()/authorize()/get_ipv4_status()/get_status()/get_firmware()/ logout() run all succeeded).
The local workaround added no coverage this device didn't already have from upstream once dependencies were current,
so it's been removed rather than kept as unused code.
"""

from __future__ import annotations
import logging
from typing import Any

from tplinkrouterc6u import TplinkRouterProvider

from .base import RouterProvider
from .connection import RouterConnection

logger = logging.getLogger(__name__)


class TplinkProvider(RouterProvider):
    """Collects WAN/gateway/DNS/firmware/uptime/client-count info from a TP-Link router's admin panel,
    via tplinkrouterc6u's auto-detection - no vendor/firmware-variant special-casing here."""

    def __init__(self, connection: RouterConnection, include_device_list: bool = False) -> None:
        """include_device_list gates the per-device MAC/hostname/IP list behind an explicit opt-in.

        Aggregate client counts (clients_total, wired_total, etc.) are collected unconditionally - they carry no per-device identity.
        The raw device list does (MAC address + hostname per connected device),
        so unlike every other field this provider collects, it's disabled by default even when the router is enabled.
        """
        self._connection = connection
        self._include_device_list = include_device_list

    @staticmethod
    def _serialize_devices(devices: list) -> list[dict[str, Any]]:
        """Convert tplinkrouterc6u Device objects into JSON-serializable dicts.

        Only the fields relevant to an identity/audit log are kept (hostname, MAC, IP, connection type, active) -
        per-device throughput/signal stats aren't audit-relevant and would just bloat the log.
        """
        return [
            {
                "hostname": device.hostname,
                "mac": device.macaddr,
                "ip": device.ipaddr,
                "connection_type": device.type.value,
                "active": device.active,
            }
            for device in devices
        ]

    def collect(self) -> dict[str, Any]:
        """Return WAN/gateway/DNS/firmware/uptime/client-count info, or {} if the router can't be reached.

        get_client() already runs one authorize()+logout() cycle internally as part of most classes'
        supports() check, leaving the returned instance logged out - authorize() here starts a fresh session
        for the actual read calls that follow, regardless of which concrete class was auto-detected.

        Any auth, network, or library error here is logged and swallowed rather than raised:
        per docs/architecture.md, collectors must fail independently without breaking the rest of the audit snapshot.
        This currently catches the broad Exception class,
        since tplinkrouterc6u's specific exception hierarchy isn't something verified against every possible failure mode
        (wrong password vs. router unreachable vs. an unsupported model) - narrowing this once real failure modes are observed would be a good follow-up.
        """
        router = None
        try:
            router = TplinkRouterProvider.get_client(
                self._connection.address,
                self._connection.password,
                self._connection.username,
                verify_ssl=self._connection.verify_tls,
                timeout=self._connection.timeout,
            )
            router.authorize()
            ipv4_status = router.get_ipv4_status()
            status = router.get_status()
            firmware = router.get_firmware()
        except Exception as error:
            logger.warning(
                "TP-Link router collection failed (%s): %s | This usually means an incorrect router "
                "username/password, or the router being unreachable at this address - double-check "
                "router.connection.address/username/password in your config.",
                self._connection.address, error,
            )
            return {}
        else:
            result = {
                "wan_ip": ipv4_status.wan_ipv4_ipaddr,
                "wan_mac": ipv4_status.wan_macaddr,
                "conn_type": ipv4_status.wan_ipv4_conntype,
                "gateway": ipv4_status.wan_ipv4_gateway,
                "dns_primary": ipv4_status.wan_ipv4_pridns,
                "dns_secondary": ipv4_status.wan_ipv4_snddns,
                "wan_uptime_seconds": status.wan_ipv4_uptime,
                "firmware_version": firmware.firmware_version,
                "hardware_version": firmware.hardware_version,
                "model": firmware.model,
                "connected_clients_total": status.clients_total,
            }
            if self._include_device_list:
                result["devices"] = self._serialize_devices(status.devices)
            return result
        finally:
            if router is not None:
                try:
                    router.logout()
                except Exception as error:
                    logger.debug("TP-Link router logout failed (non-fatal): %s", error)