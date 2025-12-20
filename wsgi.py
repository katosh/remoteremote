#!/usr/bin/env python3
"""
WSGI Entry Point für Produktionsserver (Gunicorn)

Nutzung mit Gunicorn:
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app

Mit Socket (für Nginx/Caddy):
    gunicorn -w 4 --bind unix:/tmp/tvremote.sock wsgi:app
"""
import os
import sys

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Produktionsumgebung
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = '0'

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()
