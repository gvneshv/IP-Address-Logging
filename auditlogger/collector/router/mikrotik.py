"""MikroTik router provider, backed by the librouteros RouterOS API client.

Unlike TP-Link, RouterOS has no fixed WAN port - any interface can be the WAN depending on how the device is configured,
so the interface to read WAN fields from is explicit config (router.wan_interface),
not auto-detected the way TplinkProvider's vendor library does it.

Verified against a real RouterOS 6.45.9 device (RB951Ui-2nD).
That device turned out to be running in pure bridge mode - every ether port is a bridge1 slave,
there's no default route and no dhcp-client - so on it the WAN-style fields (conn_type/gateway/dns_*) all come back None.
That's correct behavior, not a bug: this provider is written for a MikroTik acting as the *main* router (NAT'ing, holding a default route),
which this test device isn't.
The wan_ip/wan_mac lookup was still confirmed end-to-end against real hardware:
RouterOS reports an address configured on a bridge port via both "interface"
(the configured port name) and "actual-interface" (the real logical interface) - this provider matches on "interface", which is what router.wan_interface should name.

wan_uptime_seconds is intentionally always None:
RouterOS doesn't expose a "time since WAN connected" counter for a plain interface the way tplinkrouterc6u's WanStatus does for TP-Link.

Caveat: the dhcp-client branch below (conn_type="dhcp", reading gateway/DNS from an active dhcp-client lease)
is written from RouterOS's documented API property names, not verified against a live dhcp-client - the test device had none.
Flagging this so it gets re-checked against real output before being trusted, the same way the static/bridge branch already has been.
"""

from __future__ import annotations

import logging
import re
import ssl
from typing import Any

from librouteros import connect
from librouteros.exceptions import LibRouterosError

from .base import RouterProvider
from .connection import RouterConnection

logger = logging.getLogger(__name__)

_UPTIME_RE = re.compile(
    r"(?:(?P<weeks>\d+)w)?(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?"
    r"(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?"
)


def _parse_uptime_seconds(value: str | None) -> int | None:
    """Parse RouterOS's compact uptime string (e.g. "6d2h26m24s") into seconds.

    Returns None for anything that doesn't match at least one unit,
    rather than guessing - an unexpected format should surface as "field unavailable" rather than a silently wrong number.
    """
    if not value:
        return None
    match = _UPTIME_RE.fullmatch(value.strip())
    if not match or not any(match.groups()):
        return None
    parts = {key: int(val) for key, val in match.groupdict(default="0").items()}
    return (
        parts["weeks"] * 604800
        + parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


class MikrotikProvider(RouterProvider):
    """Collects identity/WAN info from a MikroTik router via the RouterOS API (librouteros)."""

    def __init__(
        self,
        connection: RouterConnection,
        wan_interface: str,
        include_device_list: bool = False,
    ) -> None:
        """wan_interface names the RouterOS interface to read WAN fields from.

        RouterOS has no fixed WAN port the way TP-Link hardware does,
        so unlike TplinkProvider this can't be auto-detected - it must be configured explicitly (router.wan_interface in config.yaml).
        """
        self._connection = connection
        self._wan_interface = wan_interface
        self._include_device_list = include_device_list

    @staticmethod
    def _resolve_port_and_ssl(connection: RouterConnection) -> tuple[int, Any]:
        """Map the shared verify_tls flag onto librouteros' port/ssl_wrapper.

        Reuses verify_tls (elsewhere meant as "verify the TLS cert") as "use the API-SSL service (port 8729) at all" here
        - MikroTik's plain API (8728) is either plaintext or you switch to the separate api-ssl service entirely,
        there's no partial option.
        Only the plaintext 8728 path has been verified against real hardware;
        the api-ssl path is untested.
        """
        if not connection.verify_tls:
            return 8728, None
        context = ssl.create_default_context()
        return 8729, context.wrap_socket

    def collect(self) -> dict[str, Any]:
        """Return identity + (if applicable) WAN info, or {} if the router can't be reached.

        Per docs/architecture.md, any failure here is logged and swallowed rather than raised,
        matching TplinkProvider - collectors must fail independently without breaking the rest of the audit snapshot.
        """
        api = None
        try:
            port, ssl_wrapper = self._resolve_port_and_ssl(self._connection)
            api = connect(
                host=self._connection.address,
                username=self._connection.username,
                password=self._connection.password,
                port=port,
                timeout=self._connection.timeout,
                ssl_wrapper=ssl_wrapper,
            )

            resource = next(iter(api.path("system", "resource")), {})
            routerboard = next(iter(api.path("system", "routerboard")), {})
            interfaces = list(api.path("interface"))
            addresses = list(api.path("ip", "address"))
            routes = list(api.path("ip", "route"))
            dns = next(iter(api.path("ip", "dns")), {})
            dhcp_clients = list(api.path("ip", "dhcp-client"))
            leases = list(api.path("ip", "dhcp-server", "lease"))
            wireless_clients = list(api.path("interface", "wireless", "registration-table"))
        except (LibRouterosError, OSError) as error:
            logger.warning(
                "MikroTik router collection failed (%s): %s | This usually means an incorrect "
                "router username/password, the router being unreachable at this address, or the "
                "RouterOS API service (IP > Services > api) being disabled - double-check "
                "router.connection.address/username/password and router.wan_interface in your config.",
                self._connection.address, error,
            )
            return {}
        finally:
            if api is not None:
                try:
                    api.close()
                except Exception as error:
                    logger.debug("MikroTik router API close failed (non-fatal): %s", error)

        result = self._build_result(resource, routerboard, interfaces, addresses, routes, dns, dhcp_clients)
        result["connected_clients_total"] = len(leases) + len(wireless_clients)
        if self._include_device_list:
            result["devices"] = self._serialize_devices(leases, wireless_clients)
        return result

    def _build_result(
        self,
        resource: dict[str, Any],
        routerboard: dict[str, Any],
        interfaces: list[dict[str, Any]],
        addresses: list[dict[str, Any]],
        routes: list[dict[str, Any]],
        dns: dict[str, Any],
        dhcp_clients: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Assemble the WAN/identity fields. Split out from collect() for testability - this part is pure (no I/O), only collect() touches the network.
        """
        wan_interface_row = next(
            (row for row in interfaces if row.get("name") == self._wan_interface), {}
        )
        wan_address_row = next(
            (row for row in addresses if row.get("interface") == self._wan_interface), {}
        )
        dhcp_client_row = next(
            (row for row in dhcp_clients if row.get("interface") == self._wan_interface), None
        )
        default_route_row = next(
            (row for row in routes if row.get("dst-address") == "0.0.0.0/0"), None
        )

        wan_ip = (wan_address_row.get("address") or "").split("/")[0] or None

        if dhcp_client_row is not None:
            # Unverified against real output - see module docstring.
            conn_type = "dhcp"
            gateway = dhcp_client_row.get("gateway")
            dns_servers = [v for v in (dhcp_client_row.get("dns-server") or "").split(",") if v]
        elif default_route_row is not None:
            conn_type = "static"
            gateway = default_route_row.get("gateway")
            dns_servers = [v for v in (dns.get("servers") or "").split(",") if v]
        else:
            # No default route and no dhcp-client bound to wan_interface:
            # this interface isn't actually routing WAN traffic
            # (e.g. a pure bridge/switch device - confirmed against real hardware, see module docstring).
            # Reporting None here rather than fabricating a value.
            conn_type = None
            gateway = None
            dns_servers = []

        return {
            "wan_ip": wan_ip,
            "wan_mac": wan_interface_row.get("mac-address"),
            "conn_type": conn_type,
            "gateway": gateway,
            "dns_primary": dns_servers[0] if len(dns_servers) > 0 else None,
            "dns_secondary": dns_servers[1] if len(dns_servers) > 1 else None,
            "wan_uptime_seconds": None,  # see module docstring
            "firmware_version": routerboard.get("current-firmware"),
            "hardware_version": routerboard.get("board-name") or resource.get("board-name"),
            "model": routerboard.get("model"),
        }

    @staticmethod
    def _serialize_devices(
        leases: list[dict[str, Any]], wireless_clients: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Combine DHCP leases and wireless registration-table entries into the same hostname/mac/ip/connection_type/active
        shape TplinkProvider._serialize_devices uses,
        so downstream consumers (logging, notifications) don't need per-vendor handling.
        """
        devices = [
            {
                "hostname": lease.get("host-name"),
                "mac": lease.get("mac-address"),
                "ip": lease.get("active-address") or lease.get("address"),
                "connection_type": "dhcp",
                "active": lease.get("status") == "bound",
            }
            for lease in leases
        ]
        devices.extend(
            {
                "hostname": None,  # not exposed by the wireless registration-table
                "mac": client.get("mac-address"),
                "ip": client.get("last-ip"),
                "connection_type": "wireless",
                "active": True,  # only currently-associated clients appear in this table
            }
            for client in wireless_clients
        )
        return devices