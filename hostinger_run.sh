#!/bin/bash
set -e

echo "=================================================="
echo "🌿 Starting Guasha House on Hostinger Web Server"
echo "=================================================="

cd "$(dirname "$0")"

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
echo "🐍 Python Version: $($PYTHON_BIN --version)"

# 3. Setup clean Virtual Environment
if [ ! -f "venv/bin/python" ]; then
    echo "📦 Creating clean Virtual Environment..."
    rm -rf venv
    "$PYTHON_BIN" -m venv venv
fi

source venv/bin/activate

# 4. Install requirements with trusted hosts and system certs
echo "📦 Installing application dependencies (FastAPI, Uvicorn, SQLAlchemy)..."
pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org

# 5. Setup .env configuration
if [ ! -f ".env" ]; then
    echo "⚙️ Setting up .env configuration..."
    cp .env.example .env
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your_secure_random_jwt_secret_key_here_minimum_32_characters/$RANDOM_KEY/g" .env
fi

# 6. Stop existing background instances
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# 7. Start Uvicorn background server
echo "🚀 Starting Guasha House server on Hostinger..."
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > uvicorn.log 2>&1 &

sleep 3

# 8. Verify status
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "=================================================="
    echo "🎉 SUCCESS! Guasha House is running on Hostinger!"
    echo "🌐 Process PID: $(pgrep -f 'uvicorn main:app')"
    echo "⚡ Speed: Running 100% on your Hostinger Server"
    echo "=================================================="
else
    echo "❌ Startup failed. Log contents:"
    cat uvicorn.log
fi
