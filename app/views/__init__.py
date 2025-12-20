"""
Views/Blueprints für die TV Remote Anwendung
"""
from .main import main_bp
from .auth import auth_bp
from .remote import remote_bp
from .schedule import schedule_bp
from .settings import settings_bp
from .api import api_bp

__all__ = ['main_bp', 'auth_bp', 'remote_bp', 'schedule_bp', 'settings_bp', 'api_bp']
