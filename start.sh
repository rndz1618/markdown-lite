#!/bin/bash
# Quick start script for Markdown Lite

set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "→ Membuat virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
else
  source venv/bin/activate
fi

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    echo "→ Membuat .env dari .env.example..."
    cp .env.example .env
  else
    echo "→ Membuat .env default..."
    cat > .env << 'EOF'
MD_ROOT=./data
MD_USER=admin
MD_PASS=changeme
PORT=8080
HOST=0.0.0.0
ENABLE_AUTH=true
EOF
  fi
  echo "⚠  Edit file .env dan ganti MD_PASS sebelum production!"
fi

mkdir -p data

echo "→ Menjalankan Markdown Lite..."
echo "  Buka http://localhost:8080 (atau IP server)"
python app.py
