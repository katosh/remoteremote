"""
Haupt-Views (Dashboard, etc.)
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

from ..models import User, Schedule, Log, TVState
from ..services.tv_service import get_tv_service

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    """Startseite - Weiterleitung zum Dashboard oder Login"""
    user = User.query.first()
    if not user:
        return redirect(url_for('auth.setup'))
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Hauptübersicht"""
    tv_service = get_tv_service()
    tv_info = None
    tv_state = TVState.get_instance()

    try:
        tv_info = tv_service.get_info()
        if tv_info:
            tv_state.power_state = tv_info.power_state
            tv_state.last_confirmed = datetime.utcnow()
    except Exception:
        pass

    # Nächste geplante Aktionen
    upcoming_schedules = Schedule.query.filter(
        Schedule.enabled == True,
        Schedule.next_run != None
    ).order_by(Schedule.next_run).limit(5).all()

    # Letzte Aktivitäten
    recent_logs = Log.query.filter(
        Log.category.in_(['action', 'schedule'])
    ).order_by(Log.timestamp.desc()).limit(10).all()

    return render_template(
        'dashboard.html',
        tv_info=tv_info,
        tv_state=tv_state,
        upcoming_schedules=upcoming_schedules,
        recent_logs=recent_logs
    )
