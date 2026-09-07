#!/bin/bash

DIR="/home/u713703050/domains/guashahouse.com/public_html"
if [ ! -d "$DIR" ]; then
    DIR="$(cd "$(dirname "$0")" && pwd)"
fi
cd "$DIR"

# 1. Locate Python
VENV_PYTHON="$DIR/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
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
    "$PYTHON_BIN" -m venv "$DIR/venv" 2>/dev/null || true
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>/dev/null || true
fi

# 2. Check if uvicorn is ALREADY responding on port 8000
if "$VENV_PYTHON" -c "import socket; s = socket.socket(); s.settimeout(0.5); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "Guasha House is already running."
    exit 0
fi

# 3. Clean any stale/dead processes
pkill -9 -f "uvicorn main:app" 2>/dev/null || true
sleep 0.5

# 4. Initialize Database
"$VENV_PYTHON" -c "from database import init_db; init_db()" 2>/dev/null || true

# 5. Boot Uvicorn Daemon fully detached
nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 < /dev/null &
disown -a 2>/dev/null || true
sleep 2

# 6. Verify socket connectivity
if "$VENV_PYTHON" -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "🎉 SUCCESS: Guasha House is ACTIVE and HEALTHY!"
else
    echo "❌ Startup failed. Log contents:"
    cat "$DIR/uvicorn.log" || true
fi
