#!/bin/sh
# Run from project root. Uses PORT from .env or 8080.
cd "$(dirname "$0")"
export PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
