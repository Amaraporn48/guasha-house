#!/bin/bash

DIR="/home/u713703050/domains/guashahouse.com/public_html"
if [ ! -d "$DIR" ]; then
    DIR="$(cd "$(dirname "$0")" && pwd)"
fi
cd "$DIR"

# Check if backend on port 8000 is genuinely healthy and responding
IS_HEALTHY=0
if python3 -c "import socket; s = socket.socket(); s.settimeout(0.5); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    IS_HEALTHY=1
fi

# If healthy, nothing to do
if [ "$IS_HEALTHY" -eq 1 ]; then
    echo "Guasha House is already running and healthy."
    exit 0
fi

# If unhealthy or stopped, kill stale zombies
echo "Cleaning up stale processes..."
pkill -9 -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# Locate Python in venv
VENV_PYTHON="$DIR/venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="$(which python3 || echo "$HOME/python/bin/python3")"
fi

# Boot fresh server
echo "🚀 Booting fresh Guasha House backend..."
nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 &
sleep 2

if python3 -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "=================================================="
    echo "🎉 SUCCESS: Guasha House is ACTIVE and HEALTHY!"
    echo "=================================================="
else
    echo "❌ Status: Log contents below:"
    cat "$DIR/uvicorn.log" || true
fi
