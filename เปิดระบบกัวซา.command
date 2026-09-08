#!/bin/bash
echo "=================================================="
echo "🌿 กำลังเปิดระบบ Guasha House บน Hostinger..."
echo "=================================================="
ssh -p 65002 u713703050@147.93.78.72 "cd domains/guashahouse.com/public_html && bash hostinger_run.sh"
echo ""
echo "=================================================="
echo "🎉 เรียบร้อย! สามารถเปิดใช้งานเว็บได้ทันที:"
echo "👉 https://guashahouse.com"
echo "👉 https://guashahouse.com/admin"
echo "=================================================="
sleep 3
