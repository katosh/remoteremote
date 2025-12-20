"""
Konfiguration für die TV Remote Anwendung
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(os.path.dirname(basedir), 'instance')


class Config:
    """Basis-Konfiguration"""
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()

    # Datenbank
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"sqlite:///{os.path.join(instance_dir, 'tvremote.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

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

    # Anwendung
    APP_NAME = 'TV Fernbedienung'


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
