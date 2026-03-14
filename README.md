# bond-blinds

A Python daemon that schedules open/close commands for RF-controlled motorized blinds via a [Bond Bridge](https://bondhome.io/). Built to work around the Bond Bridge's lack of a retry mechanism — since RF is one-way with no acknowledgment, the daemon sends each command in multiple rounds to improve reliability. Built with [Claude Code](https://claude.ai/claude-code).

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- A Bond Bridge on your local network
- Your Bond API token (found in the Bond Home app: Device → Settings → Local Control API)

## Setup

```bash
git clone <repo>
cd bond-blinds
uv sync
cp config.example.yaml config.yaml
# Edit config.yaml with your token, location, and schedule
```

## Configuration

All configuration lives in `config.yaml`. See `config.example.yaml` for a fully annotated example.

| Field | Description |
|-------|-------------|
| `bond.token` | Bond API token (required) |
| `bond.host` | Bridge IP/hostname. `null` = auto-discover via mDNS |
| `location.latitude/longitude` | Used to calculate sunrise/sunset |
| `schedule.open.reference` | `dawn` (sunrise) or `dusk` (sunset) |
| `schedule.open.offset_minutes` | Minutes before (negative) or after (positive) the reference |
| `schedule.close.reference` | `dawn` or `dusk` |
| `schedule.close.offset_minutes` | Minutes before or after the reference |
| `commands.retry_count` | Number of transmission rounds per event (default: 3) |
| `commands.retry_delay_seconds` | Seconds between rounds (default: 5) |
| `devices` | List of device IDs to control. Empty = all MS-type devices |
| `logging.file` | Log file path |
| `logging.level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

## Usage

**Run the daemon:**
```bash
uv run bond-blinds --config config.yaml
```

**Dry run** (calculates and logs the schedule without sending any commands):
```bash
uv run bond-blinds --config config.yaml --dry-run
```

**Send an immediate command** (useful for testing):
```bash
uv run bond-blinds --config config.yaml --open-now
uv run bond-blinds --config config.yaml --close-now
```

## Running at startup on macOS

Create `~/Library/LaunchAgents/com.bondhome.bond-blinds.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bondhome.bond-blinds</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/.local/bin/uv</string>
        <string>run</string>
        <string>bond-blinds</string>
        <string>--config</string>
        <string>/Users/YOUR_USERNAME/PATH_TO_PROJECT/config.yaml</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/PATH_TO_PROJECT</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/PATH_TO_PROJECT/bond-blinds.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/PATH_TO_PROJECT/bond-blinds.log</string>
</dict>
</plist>
```

Replace `YOUR_USERNAME` and `PATH_TO_PROJECT` with actual values. Find the `uv` path with `which uv`.

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.bondhome.bond-blinds.plist
```

To stop or restart:
```bash
launchctl unload ~/Library/LaunchAgents/com.bondhome.bond-blinds.plist
launchctl load ~/Library/LaunchAgents/com.bondhome.bond-blinds.plist
```

Note: LaunchAgents run after login, so enable auto-login on the machine (System Settings → Users & Groups) if you want the daemon to start without manual interaction after a reboot.
