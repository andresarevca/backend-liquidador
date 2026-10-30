#!/bin/sh
set -e

echo ">>> Ejecutando migrate..."
python manage.py migrate --noinput

echo ">>> Iniciando aplicación..."
exec "$@"
