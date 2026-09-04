#!/bin/bash
set -e

echo "=================================================="
echo "🌿 Starting Guasha House on Hostinger Web Server"
echo "=================================================="

cd "$(dirname "$0")"

# 1. Auto-install Portable Python 3.11 if system python is missing
if ! command -v python3 &> /dev/null && [ ! -f "$HOME/python/bin/python3" ]; then
    echo "📦 Downloading and installing Portable Python 3.11 on Hostinger..."
    curl -sL "https://github.com/indygreg/python-build-standalone/releases/download/20240115/cpython-3.11.7+20240115-x86_64-unknown-linux-gnu-install_only.tar.gz" | tar -xz -C "$HOME"
    echo "✅ Python 3.11 installed successfully in $HOME/python"
fi

if [ -f "$HOME/python/bin/python3" ]; then
    export PATH="$HOME/python/bin:$PATH"
fi

echo "🐍 Using: $(python3 --version 2>/dev/null || echo 'Python 3.11')"

# 2. Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "📦 Creating Virtual Environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# 3. Install requirements
echo "📦 Installing dependencies (FastAPI, Uvicorn, SQLAlchemy)..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 4. Setup .env
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env configuration..."
    cp .env.example .env
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your_secure_random_jwt_secret_key_here_minimum_32_characters/$RANDOM_KEY/g" .env
fi

# 5. Stop old instances
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# 6. Start Uvicorn background daemon
echo "🚀 Starting Guasha House server on Hostinger..."
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > uvicorn.log 2>&1 &

sleep 3

# 7. Verify status
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "=================================================="
    echo "🎉 SUCCESS! Guasha House is running on Hostinger!"
    echo "🌐 PID: $(pgrep -f 'uvicorn main:app')"
    echo "⚡ Speed: Dedicated Hostinger Server Execution"
    echo "=================================================="
else
    echo "❌ Startup log:"
    cat uvicorn.log
fi
