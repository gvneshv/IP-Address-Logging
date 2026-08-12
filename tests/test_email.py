"""Tests for EmailNotifier - smtplib is always mocked, no real SMTP connection is ever attempted."""

from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch

from auditlogger.notifications.email import EmailNotifier


class EmailNotifierTests(unittest.TestCase):
    def _complete_config(self, **overrides) -> dict:
        config = {
            "enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "user@example.com",
            "password": "secret",
            "from_address": "auditlogger@example.com",
            "to_address": "me@example.com",
        }
        config.update(overrides)
        return config

    def test_disabled_notifier_does_not_connect(self) -> None:
        """A disabled notifier should return False immediately, without touching smtplib."""
        notifier = EmailNotifier.from_config(self._complete_config(enabled=False))

        with patch("auditlogger.notifications.email.smtplib.SMTP") as mock_smtp:
            result = notifier.send_message("subject", "body")

        self.assertFalse(result)
        mock_smtp.assert_not_called()

    def test_enabled_but_incomplete_config_does_not_connect(self) -> None:
        """Enabled with a missing required field (e.g. no password) should fail closed, not attempt to connect."""
        notifier = EmailNotifier.from_config(self._complete_config(password=""))

        with patch("auditlogger.notifications.email.smtplib.SMTP") as mock_smtp:
            result = notifier.send_message("subject", "body")

        self.assertFalse(result)
        mock_smtp.assert_not_called()

    def test_complete_config_uses_starttls_by_default(self) -> None:
        """A complete, enabled config with smtp_use_ssl left at its default should use SMTP + starttls()."""
        notifier = EmailNotifier.from_config(self._complete_config())
        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server

        with patch("auditlogger.notifications.email.smtplib.SMTP", return_value=mock_server) as mock_smtp:
            result = notifier.send_message("subject", "body")

        self.assertTrue(result)
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret")
        mock_server.send_message.assert_called_once()

    def test_smtp_use_ssl_true_skips_starttls(self) -> None:
        """smtp_use_ssl: true should use SMTP_SSL and skip the starttls() call entirely."""
        notifier = EmailNotifier.from_config(self._complete_config(smtp_use_ssl=True, smtp_port=465))
        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server

        with patch("auditlogger.notifications.email.smtplib.SMTP_SSL", return_value=mock_server) as mock_smtp_ssl, \
                patch("auditlogger.notifications.email.smtplib.SMTP") as mock_smtp:
            result = notifier.send_message("subject", "body")

        self.assertTrue(result)
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 465, timeout=10)
        mock_smtp.assert_not_called()
        mock_server.starttls.assert_not_called()

    def test_smtp_exception_returns_false_without_raising(self) -> None:
        """A connection/auth failure should be caught, logged, and reported as False - never raised."""
        notifier = EmailNotifier.from_config(self._complete_config())

        with patch("auditlogger.notifications.email.smtplib.SMTP", side_effect=OSError("connection refused")):
            result = notifier.send_message("subject", "body")

        self.assertFalse(result)

    def test_message_fields_are_set_correctly(self) -> None:
        """Subject/From/To/body should reach the outgoing EmailMessage exactly as passed in."""
        notifier = EmailNotifier.from_config(self._complete_config())
        mock_server = MagicMock()
        mock_server.__enter__.return_value = mock_server

        with patch("auditlogger.notifications.email.smtplib.SMTP", return_value=mock_server):
            notifier.send_message("AuditLogger: change detected", "wan_ip: 1.2.3.4 -> 5.6.7.8")

        sent_message = mock_server.send_message.call_args[0][0]
        self.assertEqual(sent_message["Subject"], "AuditLogger: change detected")
        self.assertEqual(sent_message["From"], "auditlogger@example.com")
        self.assertEqual(sent_message["To"], "me@example.com")
        self.assertEqual(sent_message.get_content().strip(), "wan_ip: 1.2.3.4 -> 5.6.7.8")


if __name__ == "__main__":
    unittest.main()