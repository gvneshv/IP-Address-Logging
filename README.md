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
- Sends Telegram and/or email notifications on configurable triggers (WAN change by default; external IP, WAN connection type, WAN MAC, and DNS changes are opt-in) - see Configuration below
- Router/WAN data collection via the TP-Link admin panel or MikroTik's RouterOS API: WAN IP, WAN MAC, connection type (static/dynamic), gateway, primary/secondary DNS, WAN uptime (TP-Link only - see Router Configuration below), firmware/hardware version and model, and connected-client count
- Optional per-device list (MAC/hostname/IP of every connected client) - off by default, since it's more identifying data than the rest of what this tool collects; see Configuration below

## Requirements

- Windows
- Python 3.11 or newer
- [`requests`](https://pypi.org/project/requests/) (used by the router HTTP client for router admin-panel communication)
- [`librouteros`](https://pypi.org/project/librouteros/) (only needed if `router.detection.type` is `mikrotik` - speaks the RouterOS API directly, not HTTP)
- Optional: Telegram bot token and chat ID, and/or SMTP credentials, for notifications

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

`bot_token` identifies *which bot* sends the message - get it from [@BotFather](https://t.me/BotFather) (`/mybots` -> your bot -> API Token).

`chat_id` identifies *where* it sends - the chat the bot posts into, **not the bot's own ID**. For a private DM with your own bot (the common case), that's *your* numeric Telegram user ID:

1. Open a chat with your bot and send it any message (e.g. "hi") - a bot can't message you first
2. Open `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in a browser (the word `bot` stays literally in the URL, immediately followed by your token - no other text in between)
3. Find `"chat":{"id": ...}` in the response - that number is your `chat_id`

For email notifications, defaults to STARTTLS on port 587 (works with Gmail, Outlook, and most self-hosted mail servers out of the box):

```yaml
email:
  enabled: true
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_use_ssl: false  # true for implicit TLS, typically port 465
  username: "you@example.com"
  password: "YOUR_SMTP_PASSWORD"
  from_address: "you@example.com"
  to_address: "you@example.com"
```

Telegram and email are independent - enable either, both, or neither. Both fire on the same triggers (see below).

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

### MikroTik support

```yaml
router:
  enabled: true
  detection:
    type: "mikrotik"
  wan_interface: "ether1"  # required - see below
  connection:
    address: "192.168.0.1"  # bare host/IP, no scheme - MikroTik connects over the RouterOS API, not HTTP
    username: "admin"
    password: "YOUR_ADMIN_PASSWORD"
    timeout: 30
    verify_tls: false  # false = plain API on port 8728, true = API-SSL on port 8729
```

Unlike TP-Link hardware, RouterOS has no fixed WAN port - any interface can serve that role depending on how the router is configured, so it can't be auto-detected and must be named explicitly via `wan_interface`.

Before using this, make sure the RouterOS API service is enabled: **IP -> Services -> `api`** in WebFig/Winbox (port 8728 by default). It's often on by default, but worth checking.

Known limitations:
- `wan_uptime_seconds` is always `None` for MikroTik - RouterOS doesn't expose a "time since WAN connected" counter for a plain interface the way TP-Link's library does.
- If `wan_interface` isn't actually routing WAN traffic (no default route, no active DHCP client on it - e.g. the router is running as a bridge/switch rather than a NAT gateway), `conn_type`, `gateway`, `dns_primary`, and `dns_secondary` will all come back `None` rather than a guessed value.
- The DHCP-client-assigned WAN path (`conn_type: "dhcp"`) has not yet been verified against a live DHCP-client lease, only against a static-address setup and a bridge-mode device - both against real hardware.

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

AuditLogger includes a helper for creating a Windows Task Scheduler task that runs at your logon specifically (not any user's logon on the machine).

**Run this from an elevated (Administrator) terminal.** Setting an explicit run-as user (`/RU`), even for your own account, requires elevation on Windows - a non-elevated prompt fails with `ERROR: Access is denied.` This is a one-time setup step; the task itself runs later without needing elevation.

From the project root, in an elevated PowerShell:

```powershell
python -c "from auditlogger.scheduler.tasks import create_windows_startup_task; r = create_windows_startup_task(); print(r.returncode); print(r.stdout); print(r.stderr)"
```

`returncode` should be `0`. Verify the task:

```powershell
schtasks /Query /TN AuditLogger /V /FO LIST
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

Or via the GUI: **Task Scheduler -> Task Scheduler Library -> right-click "AuditLogger" -> Delete**.

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
│     │   │   ├── mikrotik.py   # MikrotikProvider - RouterOS API via librouteros
│     │   │   └── tplink.py     # TplinkProvider - wraps tplinkrouterc6u's auto-detection
│     │   ├── system.py       # Hostname, platform, boot time
│     │   └── timecheck.py    # UTC and local timestamps
│     ├── config/
│     │   ├── config.example.yaml
│     │   └── loader.py       # Config loading with a small YAML fallback
│     ├── notifications/
│     │   ├── telegram.py     # Telegram Bot API client
│     │   └── email.py        # EmailNotifier - SMTP email client
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
│     ├── test_capabilities.py
│     ├── test_email.py
│     ├── test_notification_triggers.py
│     ├── test_event.py
│     ├── test_loader.py
│     ├── test_network.py
│     └── test_router.py
├── .gitignore
├──CHANGELOG.md
├──CONTRIBUTING.md
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

Do not commit real Telegram tokens, chat IDs, SMTP credentials, or production audit logs.

## Roadmap

Planned future work:

- Full hash-chain verification across all events
- Router/WAN change detection
- Daily archives
- Report export
- Backups
- Digital signatures
- Web interface for browsing events