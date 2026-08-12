"""Application entry points for collecting and writing one audit event."""

from __future__ import annotations
import sys
from pathlib import Path

from auditlogger.collector.network import collect_network_info
from auditlogger.collector.system import collect_system_info
from auditlogger.collector.timecheck import local_now_iso, utc_now_iso
from auditlogger.config.loader import ConfigError, load_config
from auditlogger.logging_config import configure_logging
from auditlogger.notifications.email import EmailNotifier
from auditlogger.notifications.telegram import TelegramNotifier
from auditlogger.storage.hashchain import build_hashed_event
from auditlogger.storage.json_logger import JsonLogger


def build_event(config: dict) -> dict:
    """Build the unhashed audit event payload from current system state."""
    return {
        "timestamp_utc": utc_now_iso(),
        "timestamp_local": local_now_iso(),
        "network": collect_network_info(config["router"]),
        "system": collect_system_info(),
    }


def _detect_notifiable_changes(
    notifications_config: dict,
    previous_network: dict,
    current_network: dict,
) -> list[tuple[str, str, str]]:
    """Return (label, previous_value, current_value) for changes enabled in config.

    wan_change is the only trigger enabled by default when notifications_config["notify_on"] omits it - the WAN interface
    (reconnects, lease renewals, PPPoE re-auth) changes far more often than the external IP a router happens to be assigned, so it's the more useful default signal
    Every other trigger (external_ip_change, conn_type_change, wan_mac_change, dns_change) defaults to disabled and must be explicitly opted into.
    A change only counts when both a previous and current value exist and differ - a field appearing for the first time
    (e.g. router data starting to populate once a real provider lands) is not treated as a "change".
    """
    notify_on = notifications_config.get("notify_on", {})
    previous_router = previous_network.get("router", {})
    current_router = current_network.get("router", {})
    changes: list[tuple[str, str, str]] = []

    if notify_on.get("wan_change", True):
        previous_wan = previous_router.get("wan_ip")
        current_wan = current_router.get("wan_ip")
        if previous_wan and current_wan and previous_wan != current_wan:
            changes.append(("wan_ip", previous_wan, current_wan))

    if notify_on.get("external_ip_change", False):
        previous_ip = previous_network.get("external_ip")
        current_ip = current_network.get("external_ip")
        if previous_ip and current_ip and previous_ip != current_ip:
            changes.append(("external_ip", previous_ip, current_ip))

    if notify_on.get("conn_type_change", False):
        previous_conn_type = previous_router.get("conn_type")
        current_conn_type = current_router.get("conn_type")
        if previous_conn_type and current_conn_type and previous_conn_type != current_conn_type:
            changes.append(("conn_type", previous_conn_type, current_conn_type))

    if notify_on.get("wan_mac_change", False):
        previous_mac = previous_router.get("wan_mac")
        current_mac = current_router.get("wan_mac")
        if previous_mac and current_mac and previous_mac != current_mac:
            changes.append(("wan_mac", previous_mac, current_mac))

    if notify_on.get("dns_change", False):
        previous_dns = (previous_router.get("dns_primary"), previous_router.get("dns_secondary"))
        current_dns = (current_router.get("dns_primary"), current_router.get("dns_secondary"))
        if all(previous_dns) and all(current_dns) and previous_dns != current_dns:
            changes.append(("dns", ",".join(previous_dns), ",".join(current_dns)))

    return changes


def detect_capabilities(config: dict, network_info: dict) -> dict[str, object]:
    """Summarize which optional data sources produced data this run.

    This is diagnostic output for the person running AuditLogger (see docs/architecture.md's "Capability Detection" section) - it summarizes the event,
    it is never persisted into the hashed audit event itself.
    """
    router_config = config.get("router", {})
    router_info = network_info.get("router", {})
    router_enabled = bool(router_config.get("enabled", False))

    return {
        "public_ip_lookup": bool(network_info.get("external_ip")),
        "router_enabled": router_enabled,
        "router_detected": bool(router_info),
        "router_vendor": router_config.get("detection", {}).get("type") if router_enabled else None,
        "wan_ip_supported": bool(router_info.get("wan_ip")),
    }


def run_once(config_path: str | Path | None = None) -> dict:
    """Collect, hash, persist, and optionally notify for a single audit event."""
    config = load_config(config_path)
    configure_logging(config)

    logger = JsonLogger(config["storage"]["log_file"])
    previous_event = logger.read_last_event()

    event = build_event(config)
    hashed_event = build_hashed_event(event, previous_event)
    logger.append(hashed_event)

    previous_network = (previous_event or {}).get("event", {}).get("network", {})
    changes = _detect_notifiable_changes(
        config.get("notifications", {}), previous_network, event["network"]
    )

    if changes:
        message_lines = ["AuditLogger: change detected"]
        message_lines += [f"{label}: {previous} -> {current}" for label, previous, current in changes]
        message_lines.append(f"Event hash: {hashed_event['hash']}")
        message = "\n".join(message_lines)

        TelegramNotifier.from_config(config["telegram"]).send_message(message)
        EmailNotifier.from_config(config["email"]).send_message("AuditLogger: change detected", message)

    return hashed_event


def main() -> None:
    """Run the command-line entry point and print the stored event hash and capabilities.

    Configuration problems (missing config file, missing required sections, invalid YAML) are caught here
    and reported as a one-line message on stderr instead of a full traceback - for the person running this, a bad config is a setup step to fix, not a bug to debug.
    Any other exception still propagates normally, since it likely does indicate a real bug worth seeing the traceback for.
    """
    try:
        hashed_event = run_once()
        print(f"Audit event written: {hashed_event['hash']}")

        config = load_config()
        capabilities = detect_capabilities(config, hashed_event["event"]["network"])
        print("Detected capabilities:")
        for label, value in capabilities.items():
            print(f"  {label}: {value}")
    except ConfigError as error:
        print(f"AuditLogger configuration error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()