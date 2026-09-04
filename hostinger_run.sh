#!/bin/bash

echo "=================================================="
echo "🌿 Starting Guasha House on Hostinger Web Hosting"
echo "=================================================="

# Go to project directory
cd "$(dirname "$0")"

# 1. Setup Python Virtual Environment
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv || virtualenv -p python3 venv
fi

echo "📦 Activating venv and installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

# 2. Setup .env if missing
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env configuration..."
    cp .env.example .env
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your_secure_random_jwt_secret_key_here_minimum_32_characters/$RANDOM_KEY/g" .env
fi

# 3. Stop old process if running
echo "🔄 Stopping old instances..."
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

# 4. Start Uvicorn in background
echo "🚀 Starting Guasha House server..."
nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips "*" > uvicorn.log 2>&1 &

sleep 2

# 5. Check status
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo "=================================================="
    echo "✅ SUCCESS! Guasha House is running on Hostinger!"
    echo "🌐 PID: $(pgrep -f 'uvicorn main:app')"
    echo "=================================================="
else
    echo "❌ Startup error. Log output:"
    cat uvicorn.log
fi
