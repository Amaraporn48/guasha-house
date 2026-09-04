#!/bin/bash
set -e

cd "$(dirname "$0")"

# Fast check: If already running and called with keepalive, exit immediately
if [ "$1" == "--keepalive" ] && pgrep -f "uvicorn main:app" > /dev/null; then
    exit 0
fi

echo "=================================================="
echo "🌿 Starting Guasha House on Hostinger Web Server"
echo "=================================================="

# 1. Setup CA certificates path for Linux
for cert in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/ca-bundle.pem; do
    if [ -f "$cert" ]; then
        export SSL_CERT_FILE="$cert"
        export REQUESTS_CA_BUNDLE="$cert"
        export CURL_CA_BUNDLE="$cert"
        break
    fi
done

# 2. Check & Install Portable Python 3.11 if missing
if [ ! -f "$HOME/python/bin/python3" ] && ! command -v python3 &> /dev/null; then
    echo "📦 Downloading Portable Python 3.11..."
    PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240224/cpython-3.11.8%2B20240224-x86_64-unknown-linux-gnu-install_only.tar.gz"
    curl -fSL -o /tmp/cpython.tar.gz "$PYTHON_URL"
    tar -xzf /tmp/cpython.tar.gz -C "$HOME"
    rm -f /tmp/cpython.tar.gz
fi

if [ -f "$HOME/python/bin/python3" ]; then
    export PATH="$HOME/python/bin:$PATH"
fi

PYTHON_BIN="$(which python3 || echo "$HOME/python/bin/python3")"

# 3. Setup clean Virtual Environment
if [ ! -f "venv/bin/python" ]; then
    echo "📦 Creating clean Virtual Environment..."
    rm -rf venv
    "$PYTHON_BIN" -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
else
    source venv/bin/activate
fi

# 4. Setup .env configuration
if [ ! -f ".env" ]; then
    echo "⚙️ Setting up .env configuration..."
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    cat << EOF > .env
ENVIRONMENT=production
JWT_SECRET_KEY=$RANDOM_KEY
DATABASE_URL=sqlite:///./guasa_house.db
PORT=8000
EOF
fi

# Run DB initialization and seed users
python3 -c "from database import init_db; init_db()"

# 5. Stop existing instances if force restarting
if [ "$1" != "--keepalive" ]; then
    pkill -f "uvicorn main:app" 2>/dev/null || true
    sleep 1
fi

# 6. Start Uvicorn background server if not already running
if ! pgrep -f "uvicorn main:app" > /dev/null; then
    echo "🚀 Starting Guasha House server on Hostinger..."
    nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload --proxy-headers --forwarded-allow-ips "*" > uvicorn.log 2>&1 &
    sleep 2
fi

# 7. Verify status
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "=================================================="
    echo "🎉 SUCCESS! Guasha House is running on Hostinger!"
    echo "🌐 Process PID: $(pgrep -f 'uvicorn main:app')"
    echo "⚡ Status: Active 24/7"
    echo "=================================================="
else
    echo "❌ Startup failed. Log contents:"
    cat uvicorn.log
fi
