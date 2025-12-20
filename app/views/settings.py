"""
Einstellungs-Views
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required
from werkzeug.security import generate_password_hash, check_password_hash

from ..models import db, Config, User, Log, Scenario, Session
from ..services.tv_service import get_tv_service, reinit_tv_service
from ..services.logger import log_event
from ..services.discovery import discover_samsung_tvs

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
@login_required
def settings_view():
    """Einstellungen-Übersicht"""
    from flask_login import current_user

    tv = get_tv_service()
    tv_info = None
    has_token = False
    try:
        tv_info = tv.get_info()
        has_token = tv.is_paired
    except Exception:
        pass

    # Count active sessions
    session_count = Session.query.filter_by(user_id=current_user.id).count()

    return render_template(
        'settings.html',
        config={
            'tv_ip': Config.get('tv_ip', current_app.config.get('TV_IP', '')),
            'tv_mac': Config.get('tv_mac', current_app.config.get('TV_MAC', ''))
        },
        tv_info=tv_info,
        has_token=has_token,
        session_count=session_count
    )


@settings_bp.route('/tv', methods=['POST'])
@login_required
def update_tv():
    """TV-Einstellungen aktualisieren"""
    tv_ip = request.form.get('tv_ip')
    tv_mac = request.form.get('tv_mac')

    if tv_ip:
        Config.set('tv_ip', tv_ip)
    if tv_mac:
        Config.set('tv_mac', tv_mac)

    reinit_tv_service()

    log_event(
        level='INFO',
        category='config',
        message='TV-Einstellungen aktualisiert',
        details={'tv_ip': tv_ip, 'tv_mac': tv_mac},
        source='manual'
    )

    flash('TV-Einstellungen wurden aktualisiert.', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/password', methods=['POST'])
@login_required
def change_password():
    """Passwort ändern"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    user = User.query.first()

    if not check_password_hash(user.password_hash, current_password):
        flash('Aktuelles Passwort ist falsch.', 'error')
        return redirect(url_for('settings.index'))

    if len(new_password) < 8:
        flash('Das neue Passwort muss mindestens 8 Zeichen lang sein.', 'error')
        return redirect(url_for('settings.index'))

    if new_password != confirm_password:
        flash('Die neuen Passwörter stimmen nicht überein.', 'error')
        return redirect(url_for('settings.index'))

    user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    db.session.commit()

    log_event(
        level='INFO',
        category='config',
        message='Passwort geändert',
        source='manual'
    )

    flash('Passwort wurde erfolgreich geändert.', 'success')
    return redirect(url_for('settings.index'))


@settings_bp.route('/discover', methods=['POST'])
@login_required
def discover():
    """Samsung TVs im Netzwerk suchen"""
    try:
        tvs = discover_samsung_tvs()
        return jsonify({'success': True, 'tvs': tvs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/pair', methods=['POST'])
@login_required
def pair():
    """TV-Pairing starten"""
    tv = get_tv_service()

    try:
        # Pairing im Hintergrund starten
        success = tv.pair(timeout=60)

        if success:
            # Token in Config speichern
            Config.set('tv_token', tv.token)
            log_event(
                level='INFO',
                category='config',
                message='TV-Pairing erfolgreich',
                source='manual'
            )
            return jsonify({'success': True, 'message': 'Pairing erfolgreich!'})
        else:
            return jsonify({'success': False, 'error': 'Pairing fehlgeschlagen oder Timeout'})
    except Exception as e:
        log_event(
            level='ERROR',
            category='config',
            message='TV-Pairing fehlgeschlagen',
            details={'error': str(e)},
            source='manual'
        )
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/logs')
@login_required
def logs():
    """Log-Viewer"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    category = request.args.get('category', '')
    level = request.args.get('level', '')

    query = Log.query

    if category:
        query = query.filter(Log.category == category)
    if level:
        query = query.filter(Log.level == level)

    logs = query.order_by(Log.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        'logs.html',
        logs=logs,
        current_category=category,
        current_level=level
    )


@settings_bp.route('/logs/export')
@login_required
def export_logs():
    """Logs als JSON exportieren"""
    from flask import Response
    import json
    from datetime import datetime

    logs = Log.query.order_by(Log.timestamp.desc()).all()

    log_data = [{
        'timestamp': log.timestamp.isoformat(),
        'level': log.level,
        'category': log.category,
        'message': log.message,
        'details': log.get_details(),
        'client_ip': log.client_ip,
        'source': log.source
    } for log in logs]

    filename = f"tvremote_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    return Response(
        json.dumps(log_data, indent=2, ensure_ascii=False),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@settings_bp.route('/backup', methods=['POST'])
@login_required
def backup():
    """Backup erstellen und auf NAS speichern"""
    from ..services.backup import create_backup

    try:
        backup_path = create_backup()
        log_event(
            level='INFO',
            category='system',
            message='Backup erstellt',
            details={'path': backup_path},
            source='manual'
        )
        return jsonify({'success': True, 'message': 'Backup erfolgreich erstellt', 'path': backup_path})
    except Exception as e:
        log_event(
            level='ERROR',
            category='system',
            message='Backup fehlgeschlagen',
            details={'error': str(e)},
            source='manual'
        )
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/scenarios')
@login_required
def scenarios():
    """Szenarien verwalten"""
    scenarios = Scenario.query.all()
    return render_template('scenarios.html', scenarios=scenarios)


@settings_bp.route('/scenarios/create', methods=['POST'])
@login_required
def create_scenario():
    """Neues Szenario erstellen"""
    import json

    name = request.form.get('name')
    description = request.form.get('description', '')
    steps = request.form.get('steps')  # JSON string
    randomize = request.form.get('randomize_delays') == 'on'
    min_delay = int(request.form.get('min_delay_ms', 500))
    max_delay = int(request.form.get('max_delay_ms', 2000))

    scenario = Scenario(
        name=name,
        description=description,
        steps=steps,
        is_builtin=False,
        randomize_delays=randomize,
        min_delay_ms=min_delay,
        max_delay_ms=max_delay
    )

    db.session.add(scenario)
    db.session.commit()

    log_event(
        level='INFO',
        category='config',
        message=f'Szenario erstellt: {name}',
        details={'scenario_id': scenario.id},
        source='manual'
    )

    flash(f'Szenario "{name}" wurde erstellt.', 'success')
    return redirect(url_for('settings.scenarios'))


@settings_bp.route('/scenarios/<int:scenario_id>/delete', methods=['POST'])
@login_required
def delete_scenario(scenario_id: int):
    """Szenario löschen (nur benutzerdefinierte)"""
    scenario = Scenario.query.get_or_404(scenario_id)

    if scenario.is_builtin:
        return jsonify({'success': False, 'error': 'Vordefinierte Szenarien können nicht gelöscht werden.'}), 400

    name = scenario.name
    db.session.delete(scenario)
    db.session.commit()

    log_event(
        level='INFO',
        category='config',
        message=f'Szenario gelöscht: {name}',
        details={'scenario_id': scenario_id},
        source='manual'
    )

    return jsonify({'success': True})


# ============= Session Management =============

@settings_bp.route('/sessions')
@login_required
def sessions_view():
    """Aktive Sessions anzeigen"""
    from flask_login import current_user
    from ..views.auth import SESSION_COOKIE_NAME
    import hashlib

    # Get current session token to mark it
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    current_token_hash = None
    if current_token:
        current_token_hash = hashlib.sha256(current_token.encode()).hexdigest()

    # Get all active sessions for user
    sessions = Session.query.filter_by(user_id=current_user.id)\
        .order_by(Session.last_used.desc()).all()

    # Mark current session
    for session in sessions:
        session.is_current = (session.token_hash == current_token_hash)

    return render_template('sessions.html', sessions=sessions)


@settings_bp.route('/sessions/<int:session_id>/revoke', methods=['POST'])
@login_required
def revoke_session(session_id: int):
    """Einzelne Session widerrufen"""
    from flask_login import current_user
    from ..views.auth import SESSION_COOKIE_NAME
    import hashlib

    session = Session.query.get_or_404(session_id)

    # Ensure session belongs to current user
    if session.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Nicht autorisiert'}), 403

    # Check if this is the current session
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    if current_token:
        current_token_hash = hashlib.sha256(current_token.encode()).hexdigest()
        if session.token_hash == current_token_hash:
            return jsonify({'success': False, 'error': 'Aktuelle Session kann nicht widerrufen werden. Nutzen Sie "Abmelden".'}), 400

    device_name = session.device_name
    session.revoke()

    log_event(
        level='INFO',
        category='auth',
        message=f'Session widerrufen: {device_name}',
        details={'session_id': session_id},
        source='manual'
    )

    return jsonify({'success': True, 'message': f'Session "{device_name}" wurde widerrufen.'})


@settings_bp.route('/sessions/revoke-all', methods=['POST'])
@login_required
def revoke_all_sessions():
    """Alle Sessions außer der aktuellen widerrufen"""
    from flask_login import current_user
    from ..views.auth import SESSION_COOKIE_NAME
    import hashlib

    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    current_token_hash = None
    if current_token:
        current_token_hash = hashlib.sha256(current_token.encode()).hexdigest()

    # Get all sessions for user
    sessions = Session.query.filter_by(user_id=current_user.id).all()
    revoked_count = 0

    for session in sessions:
        # Don't revoke current session
        if current_token_hash and session.token_hash == current_token_hash:
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


@settings_bp.route('/sessions/api')
@login_required
def sessions_api():
    """API: Aktive Sessions als JSON"""
    from flask_login import current_user
    from ..views.auth import SESSION_COOKIE_NAME
    import hashlib

    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    current_token_hash = None
    if current_token:
        current_token_hash = hashlib.sha256(current_token.encode()).hexdigest()

    sessions = Session.query.filter_by(user_id=current_user.id)\
        .order_by(Session.last_used.desc()).all()

    result = []
    for session in sessions:
        data = session.to_dict()
        data['is_current'] = (session.token_hash == current_token_hash)
        result.append(data)

    return jsonify({'sessions': result})
