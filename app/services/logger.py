"""
Logging-Service für Aktivitätsprotokolle
"""
import json
from datetime import datetime, timedelta
from typing import Optional
from flask import request, has_request_context


def log_event(
    level: str,
    category: str,
    message: str,
    details: Optional[dict] = None,
    source: str = 'system'
):
    """
    Ereignis in der Datenbank protokollieren.

    Args:
        level: Log-Level (INFO, WARNING, ERROR)
        category: Kategorie (auth, action, schedule, config, system)
        message: Beschreibung des Ereignisses
        details: Zusätzliche Details als Dictionary
        source: Quelle (manual, schedule, system)
    """
    from ..models import db, Log

    # Client-Informationen aus dem Request-Kontext
    client_ip = None
    user_agent = None

    if has_request_context():
        client_ip = _get_client_ip()
        user_agent = request.headers.get('User-Agent', '')[:500]  # Begrenzen

    # Add session/user info to details for session-based changes
    if details is None:
        details = {}

    if has_request_context():
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                details['_user'] = current_user.username
                details['_session_id'] = request.cookies.get('session', '')[:16]
        except Exception:
            pass  # No user context available

    log_entry = Log(
        level=level,
        category=category,
        message=message,
        details=json.dumps(details) if details else None,
        client_ip=client_ip,
        user_agent=user_agent,
        source=source
    )

    db.session.add(log_entry)
    db.session.commit()


def _get_client_ip() -> str:
    """Echte Client-IP ermitteln (hinter Proxy)"""
    if request.headers.get('X-Forwarded-For'):
        # Erste IP in der Kette ist der Original-Client
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr


def cleanup_old_logs(days: int = None):
    """
    Alte Log-Einträge löschen.

    Args:
        days: Anzahl Tage zu behalten (Standard aus Config)
    """
    from flask import current_app
    from ..models import db, Log

    if days is None:
        days = current_app.config.get('LOG_RETENTION_DAYS', 365)

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    deleted = Log.query.filter(Log.timestamp < cutoff_date).delete()
    db.session.commit()

    if deleted > 0:
        log_event(
            level='INFO',
            category='system',
            message=f'{deleted} alte Log-Einträge gelöscht',
            details={'cutoff_days': days, 'deleted_count': deleted},
            source='system'
        )


def get_log_stats() -> dict:
    """Statistiken über die Logs"""
    from ..models import Log
    from sqlalchemy import func

    total = Log.query.count()

    by_level = dict(
        Log.query.with_entities(
            Log.level, func.count(Log.id)
        ).group_by(Log.level).all()
    )

    by_category = dict(
        Log.query.with_entities(
            Log.category, func.count(Log.id)
        ).group_by(Log.category).all()
    )

    return {
        'total': total,
        'by_level': by_level,
        'by_category': by_category
    }
