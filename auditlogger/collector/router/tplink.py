"""TP-Link router provider, backed by the third-party tplinkrouterc6u client.

TP-Link's admin-panel login uses a proprietary RSA/AES-encrypted password
exchange that differs across firmware generations. Rather than reimplement
that here, this wraps tplinkrouterc6u (https://github.com/AlexandrErohin/TP-Link-Archer-C6U),
an actively maintained, open-source library that already handles it and
auto-selects the right client class for the detected router model.

The Archer AX72 needs one exception:
its firmware signs login requests with nested RSA-OAEP chunking that tplinkrouterc6u doesn't implement (see tplink_ax72.py for the full writeup),
so upstream's auto-detection can't find a working client for it.
TplinkRouterAX72 is tried first as a known-good fix for that specific case;
any other TP-Link router falls back to upstream's normal auto-detection unchanged.
"""

from __future__ import annotations
import logging
from typing import Any

from tplinkrouterc6u import TplinkRouterProvider

from .base import RouterProvider
from .connection import RouterConnection
from .tplink_ax72 import TplinkRouterAX72

logger = logging.getLogger(__name__)


class TplinkProvider(RouterProvider):
    """Collects WAN IP, gateway, DNS, firmware, uptime, and client-count info from a TP-Link router's admin panel."""

    def __init__(self, connection: RouterConnection, include_device_list: bool = False) -> None:
        """include_device_list gates the per-device MAC/hostname/IP list behind an explicit opt-in.

        Aggregate client counts (clients_total, wired_total, etc.) are collected unconditionally - they carry no per-device identity.
        The raw device list does (MAC address + hostname per connected device), so unlike every other field this provider collects,
        it's disabled by default even when the router is enabled.
        """
        self._connection = connection
        self._include_device_list = include_device_list

    def _get_authorized_client(self):
        """Return an already-authorized router client, trying the confirmed AX72 fix first.

        TplinkRouterAX72.supports() (inherited unchanged from TplinkRouter) only checks that the password-key exchange succeeds,
        not the full login - it can't tell AX72 apart from any other TP-Link router on that basis.
        Only a real authorize() proves the OAEP signature scheme actually applies,
        so that's what decides here; any other TP-Link router falls back to upstream's normal auto-detection.
        """
        ax72 = TplinkRouterAX72(
            self._connection.address,
            self._connection.password,
            self._connection.username,
            verify_ssl=self._connection.verify_tls,
            timeout=self._connection.timeout,
        )
        try:
            ax72.authorize()
            return ax72
        except Exception as error:
            logger.debug(
                "TplinkRouterAX72 didn't authorize (expected for non-AX72 routers), falling back to auto-detection: %s", error
            )

        router = TplinkRouterProvider.get_client(
            self._connection.address,
            self._connection.password,
            self._connection.username,
            verify_ssl=self._connection.verify_tls,
            timeout=self._connection.timeout,
        )
        router.authorize()
        return router

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

        Makes three authenticated calls per run (get_ipv4_status, get_status, get_firmware) plus the login/logout pair
        - more router round-trips than the original WAN-only version, but all three share one authorized session,
        so this is still a single authorize()/logout() cycle, not three.

        Any auth, network, or library error here is logged and swallowed rather than raised:
        per docs/architecture.md, collectors must fail independently without breaking the rest of the audit snapshot.
        This currently catches the broad Exception class, since tplinkrouterc6u's specific exception hierarchy isn't something I've verified against a live router - narrowing this once real failure modes are observed (e.g. wrong password vs. router unreachable) would be a good follow-up.
        """
        router = None
        try:
            router = self._get_authorized_client()
            ipv4_status = router.get_ipv4_status()
            status = router.get_status()
            firmware = router.get_firmware()
        except Exception as error:
            logger.warning(
                "TP-Link router collection failed (%s): %s", self._connection.address, error
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