# AuditLogger

AuditLogger is a Windows-focused Python audit utility that records network and system identity data in tamper-evident JSONL logs. It can also notify a Telegram chat when the external IP address changes between runs.

## Features

- Runs manually or through Windows Task Scheduler at user logon
- Records external IP address
- Records local IP address
- Records the Windows adapter name associated with the selected local IP
- Records the adapter MAC address
- Records hostname, platform, and system boot time
- Writes newline-delimited JSON logs
- Adds SHA256 hashes to each stored event
- Links each event to the previous event hash
- Sends Telegram notifications when the external IP changes
- Router/WAN data collection (in progress) - see `docs/refactoring-roadmap.md`

## Requirements

- Windows
- Python 3.11 or newer
- [`requests`](https://pypi.org/project/requests/) (used by the router HTTP client for router admin-panel communication)
- Optional: Telegram bot token and chat ID for notifications

## Installation

Clone the repository, then open PowerShell in the project root:

```powershell
cd "W:\Projects\IP Address Logging"
```

Create a local config file:

```powershell
Copy-Item .\auditlogger\config\config.example.yaml .\auditlogger\config\config.yaml
```

Edit `auditlogger/config/config.yaml`.

For logging only:

```yaml
telegram:
  enabled: false
  bot_token: ""
  chat_id: ""
```

For Telegram notifications:

```yaml
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "YOUR_CHAT_ID"
```

## Usage

Run one audit event manually:

```powershell
python -m auditlogger.main
```

Logs are written to:

```text
logs/audit.jsonl
```

Each log entry contains:

- UTC timestamp
- Local timestamp with timezone offset
- External IP
- Local IP
- Adapter name
- MAC address
- Hostname
- Platform
- Boot time
- Previous event hash
- Current event hash

## Windows Startup Task

AuditLogger includes a helper for creating a Windows Task Scheduler task that runs at user logon.

From the project root:

```powershell
python -c "from auditlogger.scheduler.tasks import create_windows_startup_task; r = create_windows_startup_task(); print(r.returncode); print(r.stdout); print(r.stderr)"
```

Verify the task:

```powershell
schtasks /Query /TN AuditLogger
```

The task runs:

```powershell
python -m auditlogger.main
```

Current behavior is one run per logon. AuditLogger does not run as a continuous background service yet.

### Removing the startup task

```powershell
schtasks /Delete /TN AuditLogger /F
```

Or via the GUI: **Task Scheduler → Task Scheduler Library → right-click "AuditLogger" → Delete**.

## Project Layout

```text
IP Address Logging/
├──  auditlogger/
│     ├── collector/
│     │   ├── network.py      # External IP, local IP, adapter name, MAC address
│     │   ├── router/
│     │   │   ├── base.py       # RouterProvider - abstract provider interface
│     │   │   ├── connection.py # RouterConnection - connection/credential parameters
│     │   │   ├── client.py     # RouterClient - shared HTTP session handling
│     │   │   ├── detection.py  # AutoDetectionProvider - current default (stub)
│     │   │   ├── tplink.py     # TplinkProvider - wraps tplinkrouterc6u, AX72 fix first
│     │   │   └── tplink_ax72.py # TplinkRouterAX72 - nested RSA-OAEP signature fix
│     │   ├── system.py       # Hostname, platform, boot time
│     │   └── timecheck.py    # UTC and local timestamps
│     ├── config/
│     │   ├── config.example.yaml
│     │   └── loader.py       # Config loading with a small YAML fallback
│     ├── notifications/
│     │   ├── telegram.py     # Telegram Bot API client
│     │   └── email.py        # Future email notification placeholder
│     ├── scheduler/
│     │   └── tasks.py        # Windows Task Scheduler helper
│     ├── storage/
│     │   ├── archive.py      # Future archive placeholder
│     │   ├── hashchain.py    # Event hashing helpers
│     │   └── json_logger.py  # JSONL log storage
│     └── main.py             # Main runtime flow
├── docs/
│   ├── architecture.md
│   └── refactoring-roadmap.md
├── logs/ # gitignored
├── tests/
│     ├── test_event.py
│     ├── test_loader.py
│     ├── test_network.py
│     ├── test_router.py
│     ├── test_signature.py     # manual - offline AX72 signature/chunking checker
│     └── live_login_test.py    # manual - live end-to-end AX72 login smoke test
├── .gitignore
├──CHANGELOG.md
├──pyproject.toml
└── README.md
```

## Testing

Run the test suite:

```powershell
python -m unittest discover -s tests
```

## Security Notes

Audit logs contain sensitive local machine and network identifiers, including hostname, IP addresses, adapter name, MAC address, platform, and boot time.

The repository ignores local runtime data by default:

- `logs/`
- `auditlogger/config/config.yaml`
- `.agents/`
- Python caches

Do not commit real Telegram tokens, chat IDs, or production audit logs.

## Roadmap

Planned future work:

- Full hash-chain verification across all events
- Router/WAN change detection
- Daily archives
- Report export
- Backups
- Digital signatures
- Web interface for browsing events