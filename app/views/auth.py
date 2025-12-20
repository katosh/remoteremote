"""
Authentifizierungs-Views
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from ..models import db, User
from ..services.logger import log_event

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Anmeldeseite"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.query.first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()

            log_event(
                level='INFO',
                category='auth',
                message='Erfolgreiche Anmeldung',
                source='manual'
            )

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.dashboard'))
        else:
            log_event(
                level='WARNING',
                category='auth',
                message='Fehlgeschlagener Anmeldeversuch',
                source='manual'
            )
            flash('Ungültiges Passwort', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Abmelden"""
    log_event(
        level='INFO',
        category='auth',
        message='Benutzer abgemeldet',
        source='manual'
    )
    logout_user()
    flash('Sie wurden erfolgreich abgemeldet.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Ersteinrichtung - Passwort setzen wenn kein Benutzer existiert"""
    user = User.query.first()
    if user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        if len(password) < 8:
            flash('Das Passwort muss mindestens 8 Zeichen lang sein.', 'error')
        elif password != password_confirm:
            flash('Die Passwörter stimmen nicht überein.', 'error')
        else:
            user = User(
                username='admin',
                password_hash=generate_password_hash(password)
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

    return render_template('setup.html')
