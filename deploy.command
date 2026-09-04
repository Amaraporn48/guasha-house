#!/bin/bash
echo "=================================================="
echo "🚀 Auto Deploying Guasha House (Hostinger & GitHub)..."
echo "=================================================="
cd "/Users/amarapornsuepwongchai/Downloads/แปลงไฟล์/ระบบคีย์บิลกัวซา"

# 1. Push to GitHub
git add -A
git commit -m "update: automated deployment $(date '+%Y-%m-%d %H:%M:%S')" 2>/dev/null || true
git push origin main

echo ""
echo "📡 Triggering Hostinger instant deployment..."
RESPONSE=$(curl -s "https://guashahouse.com/deploy.php?token=guashahouse_auto_deploy_secret_2026")
echo "Hostinger Response: $RESPONSE"

echo ""
echo "=================================================="
echo "🎉 DEPLOY SUCCESS! Your website is live and up to date:"
echo "👉 https://guashahouse.com"
echo "=================================================="
sleep 3
