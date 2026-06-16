#!/bin/sh
set -e

echo ">>> Ejecutando makemigrations..."
python manage.py makemigrations --noinput

echo ">>> Ejecutando migrate..."
python manage.py migrate --noinput

echo ">>> Iniciando aplicación..."
exec "$@"
