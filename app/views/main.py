"""
Haupt-Views (Dashboard, etc.)
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

from ..models import User, Schedule, Log, TVState, Config, db
from ..services.tv_service import get_cached_status, get_tv_service, get_last_error, is_token_valid

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
    # Use cached status to avoid slow network calls
    status = get_cached_status()
    tv_info = status.get('info')
    tv_state = TVState.get_instance()

    # Update state if we got fresh info
    if tv_info and not status.get('cached'):
        tv_state.power_state = tv_info.power_state
        tv_state.last_confirmed = datetime.utcnow()
        db.session.commit()

    # Determine if TV is reachable and power state
    reachable = status['connected']
    power_state = status['power_state']
    in_transition = status.get('in_transition', False)
    transition_type = status.get('transition_type')
    just_confirmed = status.get('just_confirmed', False)
    startup_failed = status.get('startup_failed', False)

    # Check for recent errors from async operations
    last_error = get_last_error()

    # Check if TV has a valid token
    tv_has_token = is_token_valid()

    # Favorite channels (not yet implemented as model, use empty list)
    favorites = []

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
        reachable=reachable,
        power_state=power_state,
        in_transition=in_transition,
        transition_type=transition_type,
        just_confirmed=just_confirmed,
        startup_failed=startup_failed,
        last_error=last_error,
        tv_has_token=tv_has_token,
        favorites=favorites,
        schedules=upcoming_schedules,
        logs=recent_logs
    )
