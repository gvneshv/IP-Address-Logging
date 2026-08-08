"""Tests for the notification-trigger decision logic in main.py."""

from __future__ import annotations
import unittest

from auditlogger.main import _detect_notifiable_changes


class NotificationTriggerTests(unittest.TestCase):
    """Checks that _detect_notifiable_changes respects per-trigger config."""

    def test_default_config_detects_wan_change_only(self) -> None:
        """With no notify_on config, only wan_change should be enabled - external_ip_change is now opt-in."""
        previous_network = {"external_ip": "203.0.113.10", "router": {"wan_ip": "198.51.100.1"}}
        current_network = {"external_ip": "203.0.113.11", "router": {"wan_ip": "198.51.100.2"}}

        changes = _detect_notifiable_changes({}, previous_network, current_network)

        self.assertEqual(changes, [("wan_ip", "198.51.100.1", "198.51.100.2")])

    def test_external_ip_change_is_opt_in(self) -> None:
        """external_ip_change should fire once explicitly enabled, even though it's off by default."""
        notifications_config = {"notify_on": {"external_ip_change": True, "wan_change": False}}
        previous_network = {"external_ip": "203.0.113.10", "router": {"wan_ip": "198.51.100.1"}}
        current_network = {"external_ip": "203.0.113.11", "router": {"wan_ip": "198.51.100.1"}}

        changes = _detect_notifiable_changes(notifications_config, previous_network, current_network)

        self.assertEqual(changes, [("external_ip", "203.0.113.10", "203.0.113.11")])

    def test_conn_type_change_is_opt_in(self) -> None:
        """conn_type_change (static/dynamic WAN connection type) should fire once explicitly enabled."""
        notifications_config = {"notify_on": {"conn_type_change": True, "wan_change": False}}
        previous_network = {"router": {"conn_type": "dynamic"}}
        current_network = {"router": {"conn_type": "static"}}

        changes = _detect_notifiable_changes(notifications_config, previous_network, current_network)

        self.assertEqual(changes, [("conn_type", "dynamic", "static")])

    def test_wan_mac_change_is_opt_in(self) -> None:
        """wan_mac_change should fire once explicitly enabled."""
        notifications_config = {"notify_on": {"wan_mac_change": True, "wan_change": False}}
        previous_network = {"router": {"wan_mac": "AA:BB:CC:00:00:01"}}
        current_network = {"router": {"wan_mac": "AA:BB:CC:00:00:02"}}

        changes = _detect_notifiable_changes(notifications_config, previous_network, current_network)

        self.assertEqual(changes, [("wan_mac", "AA:BB:CC:00:00:01", "AA:BB:CC:00:00:02")])

    def test_dns_change_fires_when_either_server_differs(self) -> None:
        """dns_change should fire if either primary or secondary DNS differs - it's one combined trigger."""
        notifications_config = {"notify_on": {"dns_change": True, "wan_change": False}}
        previous_network = {"router": {"dns_primary": "1.1.1.1", "dns_secondary": "8.8.8.8"}}
        current_network = {"router": {"dns_primary": "1.0.0.1", "dns_secondary": "8.8.8.8"}}

        changes = _detect_notifiable_changes(notifications_config, previous_network, current_network)

        self.assertEqual(changes, [("dns", "1.1.1.1,8.8.8.8", "1.0.0.1,8.8.8.8")])

    def test_dns_change_requires_both_servers_present_on_both_sides(self) -> None:
        """A DNS field missing on either side (e.g. first-ever router read) should not count as a change."""
        notifications_config = {"notify_on": {"dns_change": True, "wan_change": False}}
        previous_network = {"router": {"dns_primary": "1.1.1.1", "dns_secondary": None}}
        current_network = {"router": {"dns_primary": "1.1.1.1", "dns_secondary": "8.8.8.8"}}

        changes = _detect_notifiable_changes(notifications_config, previous_network, current_network)

        self.assertEqual(changes, [])

    def test_disabled_trigger_is_not_reported(self) -> None:
        """A trigger explicitly disabled in config should never appear in the results."""
        notifications_config = {"notify_on": {"wan_change": False}}
        previous_network = {"external_ip": "203.0.113.10", "router": {"wan_ip": "198.51.100.1"}}
        current_network = {"external_ip": "203.0.113.10", "router": {"wan_ip": "198.51.100.2"}}

        changes = _detect_notifiable_changes(notifications_config, previous_network, current_network)

        self.assertEqual(changes, [])

    def test_missing_previous_value_does_not_count_as_a_change(self) -> None:
        """A field appearing for the first time (no prior value) should not fire a notification."""
        previous_network = {"external_ip": "203.0.113.10"}
        current_network = {"external_ip": "203.0.113.10", "router": {"wan_ip": "198.51.100.2"}}

        changes = _detect_notifiable_changes({}, previous_network, current_network)

        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()