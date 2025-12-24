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
    """Basis-Konfiguration"""
    # Flask
    SECRET_KEY = get_or_create_secret_key()

    # Babel (i18n)
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_TRANSLATION_DIRECTORIES = 'translations'
    LANGUAGES = ['en', 'de']

    # Datenbank
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

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 Stunde

    # Rate Limiting
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_DEFAULT = "200 per day"
    RATELIMIT_HEADERS_ENABLED = True

    # TV-Einstellungen (Standardwerte)
    TV_IP = os.environ.get('TV_IP') or '192.168.178.103'
    TV_PORT = int(os.environ.get('TV_PORT') or 8002)
    TV_MAC = os.environ.get('TV_MAC') or '80:47:86:E9:B2:17'
    TV_TOKEN_FILE = os.environ.get('TV_TOKEN_FILE') or os.path.join(instance_dir, 'tv_token')

    # Zeitzone
    TIMEZONE = 'Europe/Berlin'

    # Logging
    LOG_RETENTION_DAYS = 365  # 1 Jahr

    # Backup
    BACKUP_METHOD = 'ssh'  # 'ssh' oder 'local'
    BACKUP_SSH_HOST = os.environ.get('BACKUP_SSH_HOST', '')
    BACKUP_SSH_USER = os.environ.get('BACKUP_SSH_USER', '')
    BACKUP_SSH_PATH = os.environ.get('BACKUP_SSH_PATH', '')

    # Application
    APP_NAME = 'remoteRemote'


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
