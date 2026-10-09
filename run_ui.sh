#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PORT=${PORT:-8090}
echo "=========================================================="
echo "🔴 Démarrage de l'interface utilisateur rouge HL-Manager"
echo "🌐 URL locale : http://localhost:${PORT}"
echo "☁️  Connecté à  : Vertex AI Agent Engine (hl-gemini-usage / us-central1)"
echo "=========================================================="

exec ./.venv/bin/python ui/server.py
