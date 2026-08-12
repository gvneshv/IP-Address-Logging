"""Send audit notifications through SMTP email."""

from __future__ import annotations
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailNotifier:
    """Small SMTP email client controlled by project configuration.

    Defaults to STARTTLS on port 587 - what Gmail, Outlook, and most self-hosted mail servers (e.g. Postfix) expect out of the box.
    If your provider needs implicit TLS on port 465 instead, set smtp_use_ssl: true.
    """

    smtp_host: str | None
    smtp_port: int
    username: str | None
    password: str | None
    from_address: str | None
    to_address: str | None
    use_ssl: bool = False
    enabled: bool = False

    @classmethod
    def from_config(cls, config: dict) -> "EmailNotifier":
        """Create a notifier from the email section of the config file."""
        return cls(
            smtp_host=config.get("smtp_host"),
            smtp_port=int(config.get("smtp_port", 587)),
            username=config.get("username"),
            password=config.get("password"),
            from_address=config.get("from_address"),
            to_address=config.get("to_address"),
            use_ssl=bool(config.get("smtp_use_ssl", False)),
            enabled=bool(config.get("enabled")),
        )

    def send_message(self, subject: str, text: str) -> bool:
        """Send text to the configured recipient and report whether the SMTP server accepted it.

        A misconfigured-but-enabled notifier (missing host/credentials/addresses) logs a warning and returns
        False rather than raising - matches how TelegramNotifier and the router collectors fail: notification delivery problems shouldn't take down the rest of a run.
        """
        if not self.enabled:
            return False

        if not all([self.smtp_host, self.username, self.password, self.from_address, self.to_address]):
            logger.warning(
                "Email notification skipped: email.enabled is true but smtp_host/username/password/"
                "from_address/to_address aren't all set in config"
            )
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.from_address
        message["To"] = self.to_address
        message.set_content(text)

        try:
            smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
            with smtp_class(self.smtp_host, self.smtp_port, timeout=10) as server:
                if not self.use_ssl:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(message)
            return True
        except (smtplib.SMTPException, OSError, TimeoutError) as error:
            logger.warning("Email notification failed: %s", error)
            return False