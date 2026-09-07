#!/bin/bash

# Guasha House Resilient Auto-Keepalive Runner
DIR="/home/u713703050/domains/guashahouse.com/public_html"
if [ ! -d "$DIR" ]; then
    DIR="$(cd "$(dirname "$0")" && pwd)"
fi
cd "$DIR"

DATE_STR=$(date "+%Y-%m-%d %H:%M:%S")
echo "[$DATE_STR] Cron check executed" >> "$DIR/cron.log"

# 0. Auto-pull latest code from GitHub if git repo exists
if [ -d "$DIR/.git" ]; then
    git pull origin main >> "$DIR/cron.log" 2>&1 || true
fi

# 1. Locate Python / VirtualEnv
VENV_PYTHON="$DIR/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "[$DATE_STR] Setting up Python virtual environment..." >> "$DIR/cron.log"
    PYTHON_BIN=""
    for p in "$HOME/python/bin/python3" "/usr/local/bin/python3" "/usr/bin/python3" "python3"; do
        if [ -x "$p" ] || command -v "$p" &> /dev/null; then
            PYTHON_BIN="$p"
            break
        fi
    done
    if [ -z "$PYTHON_BIN" ]; then
        PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240224/cpython-3.11.8%2B20240224-x86_64-unknown-linux-gnu-install_only.tar.gz"
        curl -fSL -o /tmp/cpython.tar.gz "$PYTHON_URL"
        tar -xzf /tmp/cpython.tar.gz -C "$HOME"
        rm -f /tmp/cpython.tar.gz
        PYTHON_BIN="$HOME/python/bin/python3"
    fi
    "$PYTHON_BIN" -m venv "$DIR/venv" >> "$DIR/cron.log" 2>&1 || true
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" --trusted-host pypi.org --trusted-host files.pythonhosted.org >> "$DIR/cron.log" 2>&1 || true
fi

# 2. Check if uvicorn is ALREADY responding on port 8000
if "$VENV_PYTHON" -c "import socket; s = socket.socket(); s.settimeout(0.5); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "[$DATE_STR] Guasha House is already active on port 8000." >> "$DIR/cron.log"
    echo "Guasha House is already running."
    exit 0
fi

echo "[$DATE_STR] Port 8000 is down. Restarting backend daemon..." >> "$DIR/cron.log"

# 3. Clean any stale processes
pkill -9 -f "uvicorn main:app" 2>/dev/null || true
sleep 0.5

# 4. Initialize Database (ensures table schemas and seeds are ready)
"$VENV_PYTHON" -c "from database import init_db; init_db()" >> "$DIR/cron.log" 2>&1 || true

# 5. Boot Uvicorn Daemon with setsid/nohup for full session detachment
if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 < /dev/null &
else
    (nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 < /dev/null &)
fi
disown -a 2>/dev/null || true
sleep 2

# 6. Verify socket connectivity
if "$VENV_PYTHON" -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "[$DATE_STR] 🎉 SUCCESS: Backend successfully booted and listening on port 8000." >> "$DIR/cron.log"
    echo "🎉 SUCCESS: Guasha House is ACTIVE and HEALTHY!"
else
    echo "[$DATE_STR] ❌ Startup failed. Check uvicorn.log" >> "$DIR/cron.log"
    echo "❌ Startup failed. Log contents:"
    cat "$DIR/uvicorn.log" || true
fi
