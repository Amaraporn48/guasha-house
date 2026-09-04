#!/bin/bash
set -e

echo "=================================================="
echo "🌿 Guasha House ERP - Hostinger VPS Setup Script"
echo "=================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "📦 Installing Docker & Docker Compose..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
    echo "✅ Docker installed successfully."
fi

# Ensure .env exists
if [ ! -f .env ]; then
    echo "⚙️ Creating .env from .env.example..."
    cp .env.example .env
    RANDOM_SECRET=$(openssl rand -hex 32)
    sed -i "s/your_secure_random_jwt_secret_key_here_minimum_32_characters/$RANDOM_SECRET/g" .env
    echo "🔑 Generated strong random JWT_SECRET_KEY in .env"
    echo "⚠️ Please edit .env to configure your DATABASE_URL if using PostgreSQL!"
fi

# Build and start container
echo "🚀 Building and starting Guasha House container..."
docker compose up -d --build

echo "=================================================="
echo "✅ Guasha House is running on port 8000!"
echo "Check status: docker compose ps"
echo "View logs:    docker compose logs -f"
echo "=================================================="
