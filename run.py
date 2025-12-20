#!/usr/bin/env python3
"""
Entwicklungs-Startskript für TV Remote Control

Nutzung:
    python run.py              # Standard (Debug-Modus)
    python run.py --production # Produktionsmodus
"""
import os
import sys
import argparse

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description='TV Remote Control Server')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Host-Adresse (Standard: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port (Standard: 5000)')
    parser.add_argument('--production', action='store_true',
                        help='Produktionsmodus (Debug deaktiviert)')

    args = parser.parse_args()

    # Umgebungsvariablen setzen
    if args.production:
        os.environ['FLASK_ENV'] = 'production'
        os.environ['FLASK_DEBUG'] = '0'
    else:
        os.environ['FLASK_ENV'] = 'development'
        os.environ['FLASK_DEBUG'] = '1'

    # App importieren und starten
    from app import create_app

    app = create_app()

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║                   TV Remote Control                       ║
╠═══════════════════════════════════════════════════════════╣
║  Server: http://{args.host}:{args.port:<5}                          ║
║  Modus:  {'Produktion' if args.production else 'Entwicklung':<15}                          ║
║                                                           ║
║  Zum Beenden: Ctrl+C                                      ║
╚═══════════════════════════════════════════════════════════╝
    """)

    app.run(
        host=args.host,
        port=args.port,
        debug=not args.production,
        use_reloader=not args.production
    )


if __name__ == '__main__':
    main()
