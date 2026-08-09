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
- Sends Telegram notifications on configurable triggers (WAN change by default; external IP, WAN connection type, WAN MAC, and DNS changes are opt-in) - see Configuration below
- Router/WAN data collection via the TP-Link admin panel: WAN IP, WAN MAC, connection type (static/dynamic), gateway, primary/secondary DNS, WAN uptime, firmware/hardware version and model, and connected-client count
- Optional per-device list (MAC/hostname/IP of every connected client) - off by default, since it's more identifying data than the rest of what this tool collects; see Configuration below

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

Running without a config file, or with one missing a required section (`storage`, `telegram`, or `router`), prints a short error explaining what's missing and exits - it won't crash with a full traceback.

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

### Notification triggers

`notifications.notify_on` controls which detected changes send a Telegram notification. Any key left out of your config defaults as shown below:

```yaml
notifications:
  notify_on:
    wan_change: true          # default - the router's WAN interface, not your public IP
    external_ip_change: false
    conn_type_change: false   # static vs dynamic WAN connection type
    wan_mac_change: false
    dns_change: false
```

`wan_change` is the only trigger enabled by default. The router's WAN interface reconnects, renews its DHCP lease, or re-authenticates far more often than a public IP actually changes, so it's a more reliable signal that something happened - especially on connections where the ISP-assigned public IP can stay identical for months. Every audit run is still logged regardless of `notify_on`; these settings only control which changes send a Telegram message.

### Connected-device list (optional, off by default)

```yaml
router:
  enabled: true
  include_device_list: false  # set true to log every connected device's MAC, hostname, and IP
```

`connected_clients_total` (a count, no per-device identity) is always collected when the router is enabled. The full device list - each connected device's MAC address, hostname, and IP - is only collected when `include_device_list` is explicitly set to `true`, since it identifies every device on your network, not just the router's own WAN state. Turn it on only if you actually want that level of detail in your logs.

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
- Router WAN IP, WAN MAC, connection type, gateway, and DNS servers (when a router provider is configured and reachable)
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
│     ├── logging_config.py
│     └── main.py             # Main runtime flow
├── docs/
│   ├── architecture.md
│   └── refactoring-roadmap.md
├── logs/ # gitignored
├── tests/
│     ├── live_status_test.py
│     ├── test_capabilities.py
│     ├── test_notification_triggers.py
│     ├── test_event.py
│     ├── test_loader.py
│     ├── test_network.py
│     ├── test_router.py
│     ├── test_signature.py     # manual - offline AX72 signature/chunking checker
│     └── live_login_test.py    # manual - live end-to-end AX72 login smoke test
├── .gitignore
├──CHANGELOG.md
├──poetry.lock
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