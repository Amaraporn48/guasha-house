#!/bin/bash
set -e

echo "=================================================="
echo "🌿 Starting Guasha House on Hostinger Web Server"
echo "=================================================="

cd "$(dirname "$0")"

# 1. Download and install Portable Python 3.11 if missing
if [ ! -f "$HOME/python/bin/python3" ] && ! command -v python3 &> /dev/null; then
    echo "📦 Downloading Portable Python 3.11 (x86_64 Linux)..."
    PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20240224/cpython-3.11.8%2B20240224-x86_64-unknown-linux-gnu-install_only.tar.gz"
    
    rm -f /tmp/cpython.tar.gz
    curl -fSL -o /tmp/cpython.tar.gz "$PYTHON_URL" || wget -qO /tmp/cpython.tar.gz "$PYTHON_URL"
    
    echo "📦 Extracting Python 3.11..."
    tar -xzf /tmp/cpython.tar.gz -C "$HOME"
    rm -f /tmp/cpython.tar.gz
    echo "✅ Python 3.11 installed successfully in $HOME/python"
fi

if [ -f "$HOME/python/bin/python3" ]; then
    export PATH="$HOME/python/bin:$PATH"
fi

PYTHON_BIN="$(which python3 || echo "$HOME/python/bin/python3")"
echo "🐍 Python Binary: $PYTHON_BIN"
echo "🐍 Python Version: $($PYTHON_BIN --version)"

# 2. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "📦 Creating Virtual Environment..."
    "$PYTHON_BIN" -m venv venv
fi

source venv/bin/activate

# 3. Install requirements
echo "📦 Installing application dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Setup .env configuration
if [ ! -f ".env" ]; then
    echo "⚙️ Setting up .env configuration..."
    cp .env.example .env
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your_secure_random_jwt_secret_key_here_minimum_32_characters/$RANDOM_KEY/g" .env
fi

# 5. Stop existing instances
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# 6. Start Uvicorn background server
echo "🚀 Starting Guasha House server on Hostinger..."
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > uvicorn.log 2>&1 &

sleep 3

# 7. Verify status
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
