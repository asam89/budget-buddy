# Deployment Guide

## Prerequisites

| Requirement | Mac | Windows |
|------------|-----|---------|
| Python | `brew install python3` (3.10+) | [python.org](https://www.python.org/downloads/) installer |
| Node.js | `brew install node` (18+) | [nodejs.org](https://nodejs.org/) installer |
| Git | Pre-installed on macOS | [git-scm.com](https://git-scm.com/download/win) |

---

## Initial Setup

### 1. Clone the repo

```bash
git clone https://github.com/asam89/budget-buddy.git
cd budget-buddy
```

### 2. Set up the backend

```bash
# Mac / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | How to get it |
|----------|--------------|
| `DB_PASSPHRASE` | Generate: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SECRET_KEY` | Generate another random hex the same way |
| `PLAID_CLIENT_ID` | Sign up at https://dashboard.plaid.com (free Trial plan) |
| `PLAID_SECRET` | From your Plaid dashboard |
| `ANTHROPIC_API_KEY` | From https://console.anthropic.com (for PDF statement parsing) |

### 5. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 6. Access the app

- **From the host machine**: http://localhost:8000
- **From other devices on your LAN**: http://\<host-ip\>:8000
- **Mac with mDNS**: http://\<hostname\>.local:8000 (works out of the box)
- **Windows with mDNS**: Install [Bonjour](https://support.apple.com/kb/DL999) or use the IP address directly

On first visit, you'll be prompted to create your admin account.

---

## Auto-Start on Boot

### macOS (launchd)

Create a Launch Agent so Budget Buddy starts automatically on login:

```bash
cat > ~/Library/LaunchAgents/com.budgetbuddy.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.budgetbuddy</string>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/budget-buddy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/budget-buddy/.venv/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/budget-buddy/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/budget-buddy/logs/stderr.log</string>
</dict>
</plist>
EOF
```

Replace `/Users/YOUR_USERNAME/budget-buddy` with your actual path, then:

```bash
mkdir -p ~/budget-buddy/logs
launchctl load ~/Library/LaunchAgents/com.budgetbuddy.plist
```

To stop: `launchctl unload ~/Library/LaunchAgents/com.budgetbuddy.plist`

### Windows (Task Scheduler)

1. Open **Task Scheduler** → Create Task
2. **General tab**: Name it "Budget Buddy", check "Run whether user is logged on or not"
3. **Trigger tab**: New → "At startup"
4. **Action tab**: New →
   - Program: `C:\path\to\budget-buddy\.venv\Scripts\uvicorn.exe`
   - Arguments: `app.main:app --host 0.0.0.0 --port 8000`
   - Start in: `C:\path\to\budget-buddy`
5. Click OK and enter your Windows password when prompted

---

## Security Checklist

- [ ] **DB passphrase**: Generated a strong random passphrase in `.env`
- [ ] **Secret key**: Generated a separate random secret for session cookies
- [ ] **`.env` not committed**: Verify with `git status` — `.env` is in `.gitignore`
- [ ] **No port forwarding**: Confirm your router is NOT forwarding port 8000 to the internet
- [ ] **Firewall**: On Mac, allow incoming connections for Python in System Preferences → Security & Privacy → Firewall. On Windows, allow through Windows Defender Firewall.

---

## Updating to a New Version

> **Note**: Merging a PR on GitHub does **not** update the host machine. The
> host only gets new code when you pull it. Run the deploy step below after
> each merge you want to go live.

### Quick way (Mac / Linux): `deploy.sh`

The repo ships a `deploy.sh` that pulls `main`, updates dependencies, rebuilds
the frontend, and restarts the server (via launchd if it's managing the
process, otherwise via `nohup`):

```bash
~/budget-buddy/deploy.sh
```

### Manual way

```bash
cd /path/to/budget-buddy

# Pull latest code
git pull origin main

# Update backend dependencies
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Rebuild frontend
cd frontend && npm install && npm run build && cd ..

# Restart the server
# If using launchd (Mac):
launchctl kickstart -k gui/$(id -u)/com.budgetbuddy

# If running manually, just stop (Ctrl+C) and re-run:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Tip**: after updating the frontend, hard-refresh the browser
> (Cmd+Shift+R / Ctrl+Shift+R) so it doesn't run a cached old bundle.

The database schema updates automatically on startup (SQLAlchemy `create_all`).

> **Note**: If a future version includes a destructive migration (column removal, type change), a backup step will be included in the release notes. The app will never silently destroy data.
