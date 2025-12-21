"""
TV Remote Web Application - Flask App Factory
"""
import os
from flask import Flask, g
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy import event

from .models import db, User, init_db, ensure_tables_exist
from .config import config

login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def create_app(config_name: str = None) -> Flask:
    """Flask Application Factory"""
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Instance-Ordner erstellen
    instance_path = os.path.join(os.path.dirname(app.root_path), 'instance')
    os.makedirs(instance_path, exist_ok=True)

    # Extensions initialisieren
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Login Manager konfigurieren
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Bitte melden Sie sich an, um auf diese Seite zuzugreifen.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except OperationalError:
            # Database tables missing - try to recreate
            ensure_tables_exist()
            return None

    # Before request handler to recover from database errors
    @app.before_request
    def check_db_health():
        """Check database health and recover if needed"""
        if not hasattr(g, '_db_checked'):
            g._db_checked = True
            try:
                # Quick health check
                db.session.execute(db.text("SELECT 1"))
            except (OperationalError, PendingRollbackError):
                # Database issue - rollback and try to recover
                app.logger.warning("Database error detected, attempting recovery...")
                try:
                    db.session.rollback()
                    ensure_tables_exist()
                except Exception as e:
                    app.logger.error(f"Database recovery failed: {e}")

    # Teardown handler to clean up failed transactions
    @app.teardown_request
    def cleanup_db_session(exception=None):
        """Rollback any failed transactions to prevent PendingRollbackError"""
        if exception is not None:
            try:
                db.session.rollback()
            except Exception:
                pass

    # Blueprints registrieren
    from .views import main_bp, auth_bp, remote_bp, schedule_bp, settings_bp, api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(remote_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)

    # Datenbank initialisieren
    init_db(app)

    # Scheduler initialisieren (nicht in Tests, und nur einmal bei Werkzeug Reloader)
    if not app.config.get('TESTING'):
        # Bei Werkzeug Reloader: nur im Child-Prozess starten (WERKZEUG_RUN_MAIN='true')
        # Bei Produktion: immer starten (WERKZEUG_RUN_MAIN nicht gesetzt)
        werkzeug_main = os.environ.get('WERKZEUG_RUN_MAIN')
        if werkzeug_main is None or werkzeug_main == 'true':
            from .services.scheduler import init_scheduler
            init_scheduler(app)

    # Kontext-Prozessor für Templates
    @app.context_processor
    def inject_globals():
        # In test mode, don't try to connect to real TV
        if app.config.get('TESTING'):
            return {
                'app_name': app.config['APP_NAME'],
                'tv_connected': False,
                'tv_has_token': False
            }

        from .services.tv_service import get_tv_service, get_cached_status
        try:
            tv = get_tv_service()
            # Use cached status to avoid slow network calls on every page load
            status = get_cached_status()
            return {
                'app_name': app.config['APP_NAME'],
                'tv_connected': status['connected'],
                'tv_has_token': tv.is_paired if tv else False
            }
        except Exception:
            return {
                'app_name': app.config['APP_NAME'],
                'tv_connected': False,
                'tv_has_token': False
            }

    # Error Handler
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template('errors/500.html'), 500

    return app
