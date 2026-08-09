"""Tests for the Windows startup task command construction, without invoking real schtasks."""

from __future__ import annotations
import unittest
from unittest.mock import patch

from auditlogger.scheduler.tasks import create_windows_startup_task


class CreateWindowsStartupTaskTests(unittest.TestCase):
    """Checks the schtasks argument list, without actually calling schtasks.exe."""

    @patch("auditlogger.scheduler.tasks.subprocess.run")
    def test_command_wraps_in_cmd_and_sets_working_directory(self, mock_run) -> None:
        """The /TR value should cd into the project root before launching python, not run python bare."""
        create_windows_startup_task()

        args = mock_run.call_args[0][0]
        tr_value = args[args.index("/TR") + 1]

        self.assertTrue(tr_value.startswith("cmd.exe /c cd /d "))
        self.assertIn("-m auditlogger.main", tr_value)

    @patch("auditlogger.scheduler.tasks.subprocess.run")
    def test_ru_is_set_to_current_user(self, mock_run) -> None:
        """/RU should be present so the trigger is scoped to this user, not any user's logon."""
        create_windows_startup_task()

        args = mock_run.call_args[0][0]
        self.assertIn("/RU", args)
        ru_value = args[args.index("/RU") + 1]
        self.assertTrue(ru_value)

    @patch("auditlogger.scheduler.tasks.subprocess.run")
    def test_task_name_is_forwarded(self, mock_run) -> None:
        """A custom task_name should reach /TN unchanged."""
        create_windows_startup_task(task_name="CustomName")

        args = mock_run.call_args[0][0]
        self.assertEqual(args[args.index("/TN") + 1], "CustomName")


if __name__ == "__main__":
    unittest.main()