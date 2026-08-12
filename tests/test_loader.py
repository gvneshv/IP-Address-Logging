"""Tests for the fallback YAML loader's nested-section parsing and config validation."""

from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from auditlogger.config.loader import ConfigError, _load_simple_yaml, load_config


class LoaderNestingTests(unittest.TestCase):
    """Checks that the fallback parser supports the router config's depth."""

    def test_three_level_nesting_is_preserved(self) -> None:
        """router.connection.address should stay nested, not flatten to a string."""
        text = """
router:

  enabled: false

  connection:

      address:
      username:

  detection:

      type: auto
"""
        config = _load_simple_yaml(text)

        self.assertEqual(config["router"]["enabled"], False)
        self.assertIsInstance(config["router"]["connection"], dict)
        self.assertEqual(config["router"]["connection"]["address"], "")
        self.assertEqual(config["router"]["detection"]["type"], "auto")


class LoadConfigErrorTests(unittest.TestCase):
    """Checks that every way load_config() can fail raises ConfigError, never a bare builtin exception."""

    def test_missing_file_raises_config_error(self) -> None:
        """A config path that doesn't exist should raise ConfigError, not FileNotFoundError."""
        missing_path = Path(tempfile.gettempdir()) / "auditlogger-does-not-exist" / "config.yaml"

        with self.assertRaises(ConfigError) as context:
            load_config(missing_path)

        self.assertIn("Config file not found", str(context.exception))

    def test_incomplete_config_raises_config_error(self) -> None:
        """A config missing required sections should raise ConfigError listing what's missing, not KeyError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text("storage:\n  log_file: logs/audit.jsonl\n", encoding="utf-8")

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)

        message = str(context.exception)
        self.assertIn("router", message)
        self.assertIn("telegram", message)
        self.assertIn("email", message)

    def test_missing_required_key_within_present_section_raises_config_error(self) -> None:
        """A present-but-incomplete section (storage without log_file) should also be caught."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                "storage:\n  archive_dir: logs/archive\ntelegram:\n  enabled: false\nemail:\n  enabled: false\nrouter:\n  enabled: false\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)

        self.assertIn("storage.log_file", str(context.exception))

    def test_complete_config_loads_without_error(self) -> None:
        """A config with every required section/key present should load cleanly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                "storage:\n  log_file: logs/audit.jsonl\ntelegram:\n  enabled: false\nemail:\n  enabled: false\nrouter:\n  enabled: false\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config["storage"]["log_file"], "logs/audit.jsonl")


if __name__ == "__main__":
    unittest.main()