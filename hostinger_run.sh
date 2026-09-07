#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 1. Fast path: If already running, exit immediately (0ms)
if pgrep -f "uvicorn main:app" > /dev/null; then
    exit 0
fi

# 2. Locate Virtualenv Python
VENV_PYTHON=""
if [ -f "$DIR/venv/bin/python" ]; then
    VENV_PYTHON="$DIR/venv/bin/python"
elif [ -f "$HOME/python/bin/python3" ]; then
    VENV_PYTHON="$HOME/python/bin/python3"
elif command -v python3 &> /dev/null; then
    VENV_PYTHON="$(which python3)"
fi

# 3. If venv is missing, create it
if [ ! -f "$DIR/venv/bin/python" ]; then
    if [ -z "$VENV_PYTHON" ]; then
        PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240224/cpython-3.11.8%2B20240224-x86_64-unknown-linux-gnu-install_only.tar.gz"
        curl -fSL -o /tmp/cpython.tar.gz "$PYTHON_URL"
        tar -xzf /tmp/cpython.tar.gz -C "$HOME"
        rm -f /tmp/cpython.tar.gz
        VENV_PYTHON="$HOME/python/bin/python3"
    fi
    "$VENV_PYTHON" -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" --trusted-host pypi.org --trusted-host files.pythonhosted.org
    VENV_PYTHON="$DIR/venv/bin/python"
fi

# 4. Ensure .env exists
if [ ! -f "$DIR/.env" ]; then
    cat << EOF > "$DIR/.env"
ENVIRONMENT=production
JWT_SECRET_KEY=guasha_house_secure_production_key_2026_default_fallback
DATABASE_URL=sqlite:///./guasa_house.db
PORT=8000
EOF
fi

# 5. Fast database check
"$VENV_PYTHON" -c "from database import init_db; init_db()" 2>/dev/null || true

# 6. Boot Uvicorn daemon in background
nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 &

echo "Guasha House started successfully."
