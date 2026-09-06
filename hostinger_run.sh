#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 1. Fast check: If already running and called with --keepalive, exit immediately
if [ "$1" == "--keepalive" ] && pgrep -f "uvicorn main:app" > /dev/null; then
    exit 0
fi

echo "=================================================="
echo "🌿 Starting Guasha House Backend Server"
echo "=================================================="

# 2. Setup CA certificates
for cert in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/ca-bundle.pem; do
    if [ -f "$cert" ]; then
        export SSL_CERT_FILE="$cert"
        export REQUESTS_CA_BUNDLE="$cert"
        export CURL_CA_BUNDLE="$cert"
        break
    fi
done

# 3. Locate Python binary
PYTHON_BIN=""
for p in "$DIR/venv/bin/python" "$DIR/venv/bin/python3" "$HOME/python/bin/python3" "/usr/local/bin/python3" "/usr/bin/python3" "python3"; do
    if command -v "$p" &> /dev/null || [ -f "$p" ]; then
        PYTHON_BIN="$p"
        break
    fi
done

# If python is missing, download portable standalone python
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
    if [ ! -f "$HOME/python/bin/python3" ]; then
        echo "📦 Installing Portable Python 3.11..."
        PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240224/cpython-3.11.8%2B20240224-x86_64-unknown-linux-gnu-install_only.tar.gz"
        curl -fSL -o /tmp/cpython.tar.gz "$PYTHON_URL"
        tar -xzf /tmp/cpython.tar.gz -C "$HOME"
        rm -f /tmp/cpython.tar.gz
    fi
    PYTHON_BIN="$HOME/python/bin/python3"
fi

# 4. Setup Virtualenv
if [ ! -f "$DIR/venv/bin/python" ]; then
    echo "📦 Creating Virtual Environment..."
    rm -rf "$DIR/venv"
    "$PYTHON_BIN" -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install --upgrade pip
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" --trusted-host pypi.org --trusted-host files.pythonhosted.org
fi

VENV_PYTHON="$DIR/venv/bin/python"

# 5. Setup .env configuration
if [ ! -f "$DIR/.env" ]; then
    RANDOM_KEY=$("$VENV_PYTHON" -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || echo "guasha_default_secret_key_2026")
    cat << EOF > "$DIR/.env"
ENVIRONMENT=production
JWT_SECRET_KEY=$RANDOM_KEY
DATABASE_URL=sqlite:///./guasa_house.db
PORT=8000
EOF
fi

# 6. Initialize database tables
"$VENV_PYTHON" -c "from database import init_db; init_db()" || true

# 7. Stop existing instance if restarting
if [ "$1" != "--keepalive" ]; then
    pkill -f "uvicorn main:app" 2>/dev/null || true
    sleep 1
fi

# 8. Start Uvicorn background daemon
if ! pgrep -f "uvicorn main:app" > /dev/null; then
    echo "🚀 Booting Uvicorn backend server on 127.0.0.1:8000..."
    nohup "$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > "$DIR/uvicorn.log" 2>&1 &
    sleep 2
fi

# 9. Status verification
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "=================================================="
    echo "🎉 SUCCESS: Guasha House is ACTIVE on Hostinger!"
    echo "🌐 PID: $(pgrep -f 'uvicorn main:app')"
    echo "=================================================="
else
    echo "❌ Startup failed. Log contents:"
    cat "$DIR/uvicorn.log" || true
fi
