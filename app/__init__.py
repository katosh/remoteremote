"""
TV Remote Web Application - Flask App Factory
"""
import os
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .models import db, User, init_db
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
        return User.query.get(int(user_id))

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

    # Kontext-Prozessor für Templates
    @app.context_processor
    def inject_globals():
        from .services.tv_service import get_tv_service
        tv = get_tv_service()
        return {
            'app_name': app.config['APP_NAME'],
            'tv_connected': tv.is_connected() if tv else False,
            'tv_has_token': tv.is_paired if tv else False
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
