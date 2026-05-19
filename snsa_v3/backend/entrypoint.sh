#!/bin/sh
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SNSA Backend — DEV startup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "[1/1] Applying migrations..."
python manage.py migrate --noinput

echo "Server ready at http://0.0.0.0:8000"
exec "$@"
