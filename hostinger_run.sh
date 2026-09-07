#!/bin/bash

DIR="/home/u713703050/domains/guashahouse.com/public_html"
if [ ! -d "$DIR" ]; then
    DIR="$(cd "$(dirname "$0")" && pwd)"
fi
cd "$DIR"

# 1. Kill stale processes
echo "Cleaning up stale processes..."
pkill -9 -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# 2. Locate Python binary
PYTHON_BIN=""
for p in "$DIR/venv/bin/python" "$HOME/python/bin/python3" "/usr/local/bin/python3" "/usr/bin/python3" "python3"; do
    if [ -x "$p" ] || command -v "$p" &> /dev/null; then
        PYTHON_BIN="$p"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "📦 Installing Portable Python 3.11..."
    PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240224/cpython-3.11.8%2B20240224-x86_64-unknown-linux-gnu-install_only.tar.gz"
    curl -fSL -o /tmp/cpython.tar.gz "$PYTHON_URL"
    tar -xzf /tmp/cpython.tar.gz -C "$HOME"
    rm -f /tmp/cpython.tar.gz
    PYTHON_BIN="$HOME/python/bin/python3"
fi

# 3. Setup clean Virtual Environment and install all required modules
if [ ! -f "$DIR/venv/bin/python" ] || ! "$DIR/venv/bin/python" -c "import uvicorn, fastapi, bcrypt" 2>/dev/null; then
    echo "📦 Installing required Python packages into Virtualenv (FastAPI, Uvicorn, Bcrypt, SQLAlchemy)..."
    rm -rf "$DIR/venv"
    "$PYTHON_BIN" -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install --upgrade pip
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" --trusted-host pypi.org --trusted-host files.pythonhosted.org
fi

VENV_PYTHON="$DIR/venv/bin/python"

# 4. Initialize Database
"$VENV_PYTHON" -c "from database import init_db; init_db()" 2>/dev/null || true

# 5. Boot Uvicorn Daemon
echo "🚀 Booting Guasha House backend..."
nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 &
sleep 2

# 6. Verify socket connectivity
if python3 -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null || "$VENV_PYTHON" -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" 2>/dev/null; then
    echo "=================================================="
    echo "🎉 SUCCESS: Guasha House is ACTIVE and HEALTHY!"
    echo "=================================================="
else
    echo "❌ Startup failed. Log contents:"
    cat "$DIR/uvicorn.log" || true
fi
