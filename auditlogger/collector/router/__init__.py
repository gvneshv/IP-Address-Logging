"""Router provider orchestration: select a provider and collect router data.

This is the single entry point the rest of the application should use for router information.
Callers (e.g. the network collector) should never import a specific provider such as AutoDetectionProvider or TplinkProvider directly
- collect_router_info() owns the decision of which provider to use, so that decision only has to change in one place as vendor providers are added.
"""

from __future__ import annotations

from typing import Any

from .connection import RouterConnection
from .detection import AutoDetectionProvider
from .tplink import TplinkProvider


def _build_connection(router_config: dict[str, Any]) -> RouterConnection:
    """Build a RouterConnection from the router config's connection section."""
    connection_config = router_config.get("connection", {})

    return RouterConnection(
        address=connection_config.get("address") or "",
        username=connection_config.get("username") or "admin",
        password=connection_config.get("password") or "",
        timeout=connection_config.get("timeout") or 30,
        verify_tls=bool(connection_config.get("verify_tls", False)),
    )


def _select_provider(router_config: dict[str, Any]):
    """Return the RouterProvider instance for the configured detection type."""
    detection_type = router_config.get("detection", {}).get("type", "auto")

    match detection_type:
        case "tplink":
            return TplinkProvider(
                _build_connection(router_config),
                include_device_list=bool(router_config.get("include_device_list", False)),
            )
        case "auto":
            return AutoDetectionProvider()
        case _:
            # Vendor-specific providers (mikrotik, asus, keenetic, ...) will be added as new cases here once implemented.
            # Unknown/unsupported types fall back to auto-detection rather than failing outright.
            return AutoDetectionProvider()


def collect_router_info(router_config: dict[str, Any]) -> dict[str, Any]:
    """Collect router information using the configured provider.

    Returns an empty dict when the router feature is disabled, matching the
    "collectors fail/opt-out independently without breaking the snapshot"
    principle described in docs/architecture.md.
    """
    if not router_config.get("enabled", False):
        return {}

    provider = _select_provider(router_config)
    return provider.collect()