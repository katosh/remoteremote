"""
Authentifizierungs-Views mit persistenten Sessions
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response, g
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from ..models import db, User, Session
from ..services.logger import log_event

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Cookie name for persistent session
SESSION_COOKIE_NAME = 'tvremote_session'


def get_client_ip():
    """Get client IP address (handles proxies)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr


@auth_bp.before_app_request
def load_session_from_cookie():
    """Check for persistent session cookie and auto-login"""
    from sqlalchemy.exc import OperationalError
    from ..models import ensure_tables_exist

    try:
        # Skip if already authenticated
        if current_user.is_authenticated:
            # Mark the current session
            token = request.cookies.get(SESSION_COOKIE_NAME)
            if token:
                session = Session.validate_token(token)
                if session:
                    session.is_current = True
            return

        # Try to load session from cookie
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            session = Session.validate_token(token)
            if session:
                user = User.query.get(session.user_id)
                if user:
                    login_user(user, remember=False)
                    session.is_current = True
                    # Store session in g for current request
                    g.current_session = session
    except OperationalError:
        # Database tables missing - try to recover
        try:
            ensure_tables_exist()
        except Exception:
            pass  # Will be handled by the main request


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Anmeldeseite"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.query.first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=False)  # We handle remember ourselves
            user.last_login = datetime.utcnow()
            db.session.commit()

            # Create response
            next_page = request.args.get('next')
            response = make_response(redirect(next_page or url_for('main.dashboard')))

            # Create persistent session if "remember" is checked
            if remember:
                token, session = Session.create_session(
                    user_id=user.id,
                    user_agent=request.headers.get('User-Agent', ''),
                    client_ip=get_client_ip()
                )

                # Set cookie (90 days)
                response.set_cookie(
                    SESSION_COOKIE_NAME,
                    token,
                    max_age=90 * 24 * 60 * 60,  # 90 days
                    httponly=True,
                    secure=request.is_secure,  # Only HTTPS in production
                    samesite='Lax'
                )

                log_event(
                    level='INFO',
                    category='auth',
                    message=f'Erfolgreiche Anmeldung (persistente Session: {session.device_name})',
                    details={'device': session.device_name, 'session_id': session.id},
                    source='manual'
                )
            else:
                log_event(
                    level='INFO',
                    category='auth',
                    message='Erfolgreiche Anmeldung (Sitzung)',
                    source='manual'
                )

            return response
        else:
            log_event(
                level='WARNING',
                category='auth',
                message='Fehlgeschlagener Anmeldeversuch',
                source='manual'
            )
            error = 'Ungültiges Passwort'

    return render_template('login.html', error=error)


@auth_bp.route('/logout')
@login_required
def logout():
    """Abmelden und Session löschen"""
    # Revoke the current session
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        session = Session.validate_token(token)
        if session:
            session.revoke()
            log_event(
                level='INFO',
                category='auth',
                message='Benutzer abgemeldet (Session widerrufen)',
                details={'session_id': session.id},
                source='manual'
            )

    logout_user()

    # Clear cookie
    response = make_response(redirect(url_for('auth.login')))
    response.delete_cookie(SESSION_COOKIE_NAME)

    flash('Sie wurden erfolgreich abgemeldet.', 'success')
    return response


@auth_bp.route('/logout-all', methods=['POST'])
@login_required
def logout_all():
    """Alle Sessions beenden (außer aktuelle)"""
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    current_session = None

    if current_token:
        current_session = Session.validate_token(current_token)

    # Delete all sessions for user except current
    sessions = Session.query.filter_by(user_id=current_user.id).all()
    revoked_count = 0

    for session in sessions:
        if current_session and session.id == current_session.id:
            continue
        session.revoke()
        revoked_count += 1

    log_event(
        level='INFO',
        category='auth',
        message=f'{revoked_count} Sessions widerrufen',
        source='manual'
    )

    flash(f'{revoked_count} Sitzung(en) wurden beendet.', 'success')
    return redirect(url_for('settings.sessions_view'))


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Ersteinrichtung - Passwort setzen wenn kein Benutzer existiert"""
    user = User.query.first()
    if user:
        return redirect(url_for('auth.login'))

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        if len(password) < 8:
            error = 'Das Passwort muss mindestens 8 Zeichen lang sein.'
        elif password != password_confirm:
            error = 'Die Passwörter stimmen nicht überein.'
        else:
            user = User(
                username='admin',
                password_hash=generate_password_hash(password, method='pbkdf2:sha256')
            )
            db.session.add(user)
            db.session.commit()

            log_event(
                level='INFO',
                category='system',
                message='Ersteinrichtung abgeschlossen - Admin-Benutzer erstellt',
                source='system'
            )

            flash('Passwort erfolgreich gesetzt. Sie können sich jetzt anmelden.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('setup.html', error=error)
