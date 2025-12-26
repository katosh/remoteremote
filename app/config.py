"""
Konfiguration für die TV Remote Anwendung
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(os.path.dirname(basedir), 'instance')


def get_or_create_secret_key():
    """Get SECRET_KEY from env, file, or generate and save a new one."""
    # 1. Check environment variable
    if os.environ.get('SECRET_KEY'):
        return os.environ.get('SECRET_KEY')

    # 2. Check/create file-based key (persists across restarts)
    key_file = os.path.join(instance_dir, '.secret_key')
    os.makedirs(instance_dir, exist_ok=True)

    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            return f.read().strip()

    # 3. Generate new key and save it
    new_key = os.urandom(32).hex()
    with open(key_file, 'w') as f:
        f.write(new_key)
    return new_key


class Config:
    """Base configuration"""
    # Application
    APP_NAME = 'remoteRemote'

    # Flask
    SECRET_KEY = get_or_create_secret_key()

    # Babel (i18n)
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_TRANSLATION_DIRECTORIES = 'translations'
    LANGUAGES = ['en', 'de', 'es', 'fr']

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"sqlite:///{os.path.join(instance_dir, 'tvremote.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite engine options for better concurrency
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'timeout': 30,  # Wait up to 30 seconds for locks
            'check_same_thread': False  # Allow multi-threaded access
        },
        'pool_pre_ping': True  # Verify connections before use
    }

    # Session & Authentication
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)  # Session timeout
    REMEMBER_ME_DURATION_DAYS = 90  # "Remember me" token validity
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour

    # Rate Limiting (Flask-Limiter)
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_DEFAULT = "200 per day"
    RATELIMIT_HEADERS_ENABLED = True

    # Rate Limits per endpoint category
    RATELIMIT_API_STATUS = "180 per minute"  # Status polling (3/sec)
    RATELIMIT_API_DATA = "60 per minute"  # General data endpoints
    RATELIMIT_API_HEALTH = "30 per minute"  # Health checks
    RATELIMIT_REMOTE_KEY = "120 per minute"  # Key presses (2/sec)
    RATELIMIT_REMOTE_ACTION = "60 per minute"  # Power, volume, etc.
    RATELIMIT_AUTH = "5 per minute"  # Login attempts

    # TV defaults (can be overridden via UI or environment)
    TV_IP = os.environ.get('TV_IP', '')
    TV_PORT = int(os.environ.get('TV_PORT') or 8002)
    TV_MAC = os.environ.get('TV_MAC', '')
    TV_TOKEN_FILE = os.environ.get('TV_TOKEN_FILE') or os.path.join(instance_dir, 'tv_token')

    # Timezone (default, configurable via UI)
    TIMEZONE = 'Europe/Berlin'

    # Logging & Retention
    LOG_RETENTION_DAYS = 365  # Activity log retention (1 year)


class DevelopmentConfig(Config):
    """Entwicklungs-Konfiguration"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Für lokale Entwicklung ohne HTTPS


class ProductionConfig(Config):
    """Produktions-Konfiguration"""
    DEBUG = False


class TestingConfig(Config):
    """Test-Konfiguration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_COOKIE_SECURE = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
