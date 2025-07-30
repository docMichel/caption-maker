#!/bin/bash
# ~/caption-maker/start_daemon.sh

cd "$(dirname "$0")"

# Activer venv
source venv/bin/activate

# Tuer ancienne instance
pkill -f caption_server.py

# Lancer en arrière-plan avec logs
nohup python src/caption_server.py > logs/caption_server.log 2>&1 &

echo "✅ Caption server lancé (PID: $!)"
echo "📝 Logs: tail -f logs/caption_server.log"