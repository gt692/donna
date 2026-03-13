#!/bin/bash
# Donna Deploy-Script
# Verwendung: ./deploy.sh
# Voraussetzung: git push origin main wurde lokal ausgeführt

set -e

VPS="root@187.124.164.248"
APP_DIR="/opt/donna"

echo "Deploying Donna..."

ssh "$VPS" << 'ENDSSH'
set -e
cd /opt/donna
echo "→ Code aktualisieren..."
git pull origin main

echo "→ Requirements installieren..."
cd donna
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/pip install -r requirements/production.txt -q

echo "→ Migrations durchführen..."
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py migrate --noinput

echo "→ Static Files sammeln..."
DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py collectstatic --noinput -v 0

echo "→ Dienst neu starten..."
systemctl restart donna

echo "✓ Deployment abgeschlossen!"
ENDSSH
