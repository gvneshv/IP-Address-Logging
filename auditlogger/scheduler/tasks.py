"""Windows Task Scheduler helpers for installing AuditLogger startup runs."""

from __future__ import annotations
import getpass
import subprocess
import sys
from pathlib import Path


def create_windows_startup_task(task_name: str = "AuditLogger") -> subprocess.CompletedProcess[str]:
    """Create or replace a limited-privilege task that runs at the current user's logon.

    The task's action is wrapped in `cmd.exe /c cd /d "<project_root>" && ...` rather than invoking python directly:
    Task Scheduler's default "start in" folder for a bare executable target is the executable's own directory (wherever python.exe lives), not this project,
    and config.example.yaml's storage.log_file is a relative path ("logs/audit.jsonl") resolved against the process actual working directory at runtime.
    Without this, a logon-triggered run would very likely write logs under the Python install directory instead of here.

    /RU is set to the current user explicitly: /SC ONLOGON without /RU triggers on *any* user's logon to the machine,
    not just this one - not what a personal single-user audit tool should do.
    Combined with an interactive ONLOGON trigger for the current user,
    Windows can normally use a passwordless S4U logon here instead of prompting for /RP - but this hasn't been confirmed against a real machine,
    so verify once after running this and re-check with `schtasks /Query /TN AuditLogger /V /FO LIST` if it behaves unexpectedly.
    """
    project_root = Path(__file__).resolve().parents[2]
    command = f'cmd.exe /c cd /d "{project_root}" && "{sys.executable}" -m auditlogger.main'
    current_user = getpass.getuser()

    return subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/SC",
            "ONLOGON",
            "/RU",
            current_user,
            "/TR",
            command,
            "/RL",
            "LIMITED",
            "/F",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )