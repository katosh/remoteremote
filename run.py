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
import warnings

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def print_banner(host: str, port: int, production: bool):
    """Print startup banner with proper alignment."""
    width = 57  # Inner width of the box

    url = f"http://{host}:{port}"
    mode = "Produktion" if production else "Entwicklung (Debug)"

    def line(text: str) -> str:
        """Create a properly padded line."""
        return f"║  {text:<{width - 4}}  ║"

    print()
    print("╔" + "═" * width + "╗")
    print(f"║{'TV Remote Control':^{width}}║")
    print("╠" + "═" * width + "╣")
    print(line(f"Server: {url}"))
    print(line(f"Modus:  {mode}"))
    if not production:
        print(line(""))
        print(line("Auto-Reload aktiv"))
    print("╚" + "═" * width + "╝")
    print()


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

    # Suppress flask-limiter in-memory warning in development
    warnings.filterwarnings('ignore', message='.*in-memory storage.*')

    # App importieren und starten
    from app import create_app
    app = create_app()

    # Only print banner on main process (not reloader child)
    is_reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if not is_reloader_child:
        print_banner(args.host, args.port, args.production)

    # Run with minimal Flask output
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING if not args.production else logging.ERROR)

    app.run(
        host=args.host,
        port=args.port,
        debug=not args.production,
        use_reloader=not args.production
    )


if __name__ == '__main__':
    main()
