#!/bin/bash

DIR="/home/u713703050/domains/guashahouse.com/public_html"
if [ ! -d "$DIR" ]; then
    DIR="$(cd "$(dirname "$0")" && pwd)"
fi
cd "$DIR"

# 1. If already running, exit immediately
if pgrep -f "uvicorn main:app" > /dev/null 2>&1; then
    exit 0
fi

# 2. Locate Virtualenv Python
VENV_PYTHON="$DIR/venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    for p in "$HOME/python/bin/python3" "/usr/local/bin/python3" "/usr/bin/python3" "python3"; do
        if command -v "$p" &> /dev/null || [ -f "$p" ]; then
            VENV_PYTHON="$p"
            break
        fi
    done
fi

# 3. Boot detached daemon with setsid so process lives forever
if command -v setsid > /dev/null 2>&1; then
    setsid "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 &
else
    nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 &
fi
disown -a 2>/dev/null || true
