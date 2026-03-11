#!/bin/bash
cd "$(dirname "$0")"

# 起動時にアクセス用URLを表示（同じネットワークの他端末用）
echo "=========================================="
echo "  訪問看護 月次報告書 自動作成"
echo "=========================================="
echo "このPCで開く: http://127.0.0.1:8000"
LAN_IP=""
if command -v ipconfig &>/dev/null; then
  for iface in en0 en1 en2 en3; do
    LAN_IP=$(ipconfig getifaddr "$iface" 2>/dev/null)
    [ -n "$LAN_IP" ] && break
  done
fi
if [ -z "$LAN_IP" ] && command -v hostname &>/dev/null; then
  LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$LAN_IP" ] && command -v ifconfig &>/dev/null; then
  LAN_IP=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
fi
if [ -n "$LAN_IP" ]; then
  echo "他の端末で開く: http://${LAN_IP}:8000"
  echo "  （上記URLを共有すると、同じWi-Fiの人が開けます）"
else
  echo "他の端末で開く: http://このPCのIP:8000"
  echo "  （ターミナルで「ifconfig」の inet を確認してください）"
fi
echo "=========================================="
echo ""

./venv/bin/uvicorn main:app --reload --reload-dir backend --host 0.0.0.0 --port 8000 --app-dir backend
