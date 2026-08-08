"""Tests for router provider orchestration."""

from __future__ import annotations
import unittest
from unittest.mock import patch

from auditlogger.collector.router import collect_router_info


class RouterOrchestrationTests(unittest.TestCase):
    """Checks that collect_router_info respects config and delegates to a provider."""

    def test_disabled_router_returns_empty_dict(self) -> None:
        """A disabled router config should never invoke a provider."""
        self.assertEqual(collect_router_info({"enabled": False}), {})

    @patch("auditlogger.collector.router.AutoDetectionProvider.collect", return_value={"wan_ip": "10.0.0.1"})
    def test_enabled_auto_detection_delegates_to_provider(self, _mock_collect) -> None:
        """An enabled auto-detection config should return the provider's collected data."""
        result = collect_router_info({"enabled": True, "detection": {"type": "auto"}})

        self.assertEqual(result, {"wan_ip": "10.0.0.1"})

    @patch("auditlogger.collector.router.TplinkProvider.collect", return_value={"wan_ip": "203.0.113.5"})
    def test_enabled_tplink_detection_delegates_to_provider(self, _mock_collect) -> None:
        """An enabled tplink config should build a connection and return the provider's data."""
        result = collect_router_info(
            {
                "enabled": True,
                "detection": {"type": "tplink"},
                "connection": {
                    "address": "http://192.168.0.1",
                    "username": "admin",
                    "password": "secret",
                    "timeout": 30,
                    "verify_tls": False,
                },
            }
        )

        self.assertEqual(result, {"wan_ip": "203.0.113.5"})

    @patch("auditlogger.collector.router.TplinkProvider")
    def test_include_device_list_reaches_tplink_provider(self, mock_provider_class) -> None:
        """router.include_device_list should be forwarded to TplinkProvider's constructor unchanged."""
        mock_provider_class.return_value.collect.return_value = {}

        collect_router_info(
            {
                "enabled": True,
                "detection": {"type": "tplink"},
                "include_device_list": True,
                "connection": {
                    "address": "http://192.168.0.1",
                    "username": "admin",
                    "password": "secret",
                    "timeout": 30,
                    "verify_tls": False,
                },
            }
        )

        _, kwargs = mock_provider_class.call_args
        self.assertTrue(kwargs["include_device_list"])

    @patch("auditlogger.collector.router.TplinkProvider")
    def test_include_device_list_defaults_false(self, mock_provider_class) -> None:
        """Omitting include_device_list from config should default to False, not crash or default True."""
        mock_provider_class.return_value.collect.return_value = {}

        collect_router_info(
            {
                "enabled": True,
                "detection": {"type": "tplink"},
                "connection": {
                    "address": "http://192.168.0.1",
                    "username": "admin",
                    "password": "secret",
                    "timeout": 30,
                    "verify_tls": False,
                },
            }
        )

        _, kwargs = mock_provider_class.call_args
        self.assertFalse(kwargs["include_device_list"])


if __name__ == "__main__":
    unittest.main()