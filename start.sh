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
  echo "→ Membuat .env dari contoh..."
  cp .env.example .env
  echo "⚠  Edit file .env dan ganti password sebelum production!"
fi

# Create default data dir if using relative path
mkdir -p data

echo "→ Menjalankan Markdown Lite..."
echo "  Buka http://localhost:8080 (atau IP server)"
python app.py
