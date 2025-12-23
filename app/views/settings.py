"""
Settings Views
"""
import os
import time
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required
from flask_babel import gettext as _
from werkzeug.security import generate_password_hash, check_password_hash

from ..models import db, Config, User, Log, Session
from ..services.tv_service import get_tv_service, reinit_tv_service
from ..services.logger import log_event
from ..services.discovery import discover_samsung_tvs, discover_all_tvs

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
@login_required
def settings_view():
    """Einstellungen-Übersicht"""
    from flask_login import current_user
    from ..services.tv_service import get_current_tv_type

    tv = get_tv_service()
    tv_info = None
    # Don't block on get_info() - just check if paired (fast, no network call)
    has_token = tv.is_paired

    # Count active sessions
    session_count = Session.query.filter_by(user_id=current_user.id).count()

    return render_template(
        'settings.html',
        config={
            'tv_type': Config.get('tv_type', 'samsung'),
            'tv_ip': Config.get('tv_ip', current_app.config.get('TV_IP', '')),
            'tv_mac': Config.get('tv_mac', current_app.config.get('TV_MAC', ''))
        },
        tv_info=tv_info,
        has_token=has_token,
        session_count=session_count
    )


@settings_bp.route('/language', methods=['POST'])
@login_required
def change_language():
    """Change interface language"""
    from .. import LANGUAGES

    language = request.form.get('language')

    if language not in LANGUAGES:
        flash(_('Invalid language selected.'), 'error')
        return redirect(url_for('settings.settings_view'))

    Config.set('user_language', language)

    log_event(
        level='INFO',
        category='config',
        message=_('Language changed'),
        details={'language': language, 'language_name': LANGUAGES[language]},
        source='manual'
    )

    flash(_('Language changed successfully.'), 'success')
    return redirect(url_for('settings.settings_view'))


@settings_bp.route('/tv', methods=['POST'])
@login_required
def update_tv():
    """TV-Einstellungen aktualisieren"""
    tv_type = request.form.get('tv_type', 'samsung')
    tv_ip = request.form.get('tv_ip')
    tv_mac = request.form.get('tv_mac')

    # Validate TV type
    if tv_type not in ('samsung', 'philips'):
        tv_type = 'samsung'

    Config.set('tv_type', tv_type)
    if tv_ip:
        Config.set('tv_ip', tv_ip)
    if tv_mac:
        Config.set('tv_mac', tv_mac)

    reinit_tv_service()

    log_event(
        level='INFO',
        category='config',
        message='TV-Einstellungen aktualisiert',
        details={'tv_type': tv_type, 'tv_ip': tv_ip, 'tv_mac': tv_mac},
        source='manual'
    )

    flash('TV-Einstellungen wurden aktualisiert.', 'success')
    return redirect(url_for('settings.settings_view'))


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
        return redirect(url_for('settings.settings_view'))

    if len(new_password) < 8:
        flash('Das neue Passwort muss mindestens 8 Zeichen lang sein.', 'error')
        return redirect(url_for('settings.settings_view'))

    if new_password != confirm_password:
        flash('Die neuen Passwörter stimmen nicht überein.', 'error')
        return redirect(url_for('settings.settings_view'))

    user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    db.session.commit()

    log_event(
        level='INFO',
        category='config',
        message='Passwort geändert',
        source='manual'
    )

    flash('Passwort wurde erfolgreich geändert.', 'success')
    return redirect(url_for('settings.settings_view'))


@settings_bp.route('/discover', methods=['POST'])
@login_required
def discover():
    """TVs im Netzwerk suchen (Samsung und Philips)"""
    from ..services.discovery import get_tv_details

    try:
        tvs = discover_all_tvs()

        # Get detailed info (including MAC) for Samsung TVs
        for tv in tvs:
            if tv.get('type') == 'samsung' and not tv.get('mac'):
                try:
                    details = get_tv_details(tv['ip'])
                    if details.get('mac') and details['mac'] != 'Unknown':
                        tv['mac'] = details['mac']
                    if details.get('name') and details['name'] != 'Unknown':
                        tv['name'] = details['name']
                    if details.get('model') and details['model'] != 'Unknown':
                        tv['model'] = details['model']
                except Exception:
                    pass

        # Return HTML for HTMX, JSON otherwise
        if request.headers.get('HX-Request'):
            return render_template('partials/discovery_result.html', tvs=tvs, error=None)
        return jsonify({'success': True, 'tvs': tvs})
    except Exception as e:
        if request.headers.get('HX-Request'):
            return render_template('partials/discovery_result.html', tvs=None, error=str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/pair', methods=['POST'])
@login_required
def pair():
    """TV-Pairing starten (Samsung)"""
    tv = get_tv_service()

    try:
        # Clear existing token to force new pairing request
        token_file = current_app.config.get('TV_TOKEN_FILE', '~/.tv_token')
        token_file = os.path.expanduser(token_file)
        print(f"[Pairing] Clearing old token from: {token_file}", flush=True)

        # Clear token from file
        try:
            if os.path.exists(token_file):
                os.remove(token_file)
                print(f"[Pairing] Old token file removed", flush=True)
        except Exception as e:
            print(f"[Pairing] Could not remove token file: {e}", flush=True)

        # Clear token from database
        try:
            config = Config.query.get('tv_token')
            if config:
                db.session.delete(config)
                db.session.commit()
        except Exception:
            db.session.rollback()

        # Clear token from TV instance and reinitialize
        tv._token = None
        reinit_tv_service()
        tv = get_tv_service()

        # Pairing im Hintergrund starten
        success = tv.pair(timeout=60)

        if success:
            # Token in Config speichern (backup in database)
            Config.set('tv_token', tv.token)

            # Reinitialize TV service to ensure token is loaded
            reinit_tv_service()

            log_event(
                level='INFO',
                category='config',
                message='TV-Pairing erfolgreich',
                details={'token_file': token_file},
                source='manual'
            )

            # Return HTML for HTMX with auto-reload
            return '''
            <div class="p-4 bg-green-900/30 border border-green-700 rounded-xl text-green-400">
                <div class="flex items-center gap-3">
                    <svg class="w-6 h-6 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <div>
                        <p class="font-medium">Kopplung erfolgreich!</p>
                        <p class="text-sm opacity-80">Die Seite wird neu geladen...</p>
                    </div>
                </div>
            </div>
            <script>setTimeout(function() { location.reload(); }, 1500);</script>
            '''
        else:
            log_event(
                level='WARNING',
                category='config',
                message='TV-Pairing fehlgeschlagen - Timeout oder abgelehnt',
                source='manual'
            )

            return '''
            <div class="p-4 bg-yellow-900/30 border border-yellow-700 rounded-xl text-yellow-400">
                <div class="flex items-start gap-3">
                    <svg class="w-6 h-6 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                    </svg>
                    <div>
                        <p class="font-medium">Kopplung fehlgeschlagen</p>
                        <p class="text-sm mt-1 opacity-80">Zeitüberschreitung oder Anfrage wurde auf dem TV abgelehnt. Bitte erneut versuchen.</p>
                    </div>
                </div>
            </div>
            '''
    except Exception as e:
        log_event(
            level='ERROR',
            category='config',
            message='TV-Pairing fehlgeschlagen',
            details={'error': str(e)},
            source='manual'
        )

        error_msg = str(e).replace('<', '&lt;').replace('>', '&gt;')
        return f'''
        <div class="p-4 bg-red-900/30 border border-red-700 rounded-xl text-red-400">
            <div class="flex items-start gap-3">
                <svg class="w-6 h-6 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <div>
                    <p class="font-medium">Fehler bei der Kopplung</p>
                    <p class="text-sm mt-1 opacity-80">{error_msg}</p>
                </div>
            </div>
        </div>
        '''


# Store pending Philips pairing sessions with threading support
import threading
_philips_pairing_sessions = {}
_philips_pairing_lock = threading.Lock()


@settings_bp.route('/pair/philips/start', methods=['POST'])
@login_required
def pair_philips_start():
    """Start Philips TV pairing - initiates connection and shows PIN on TV"""
    import secrets
    from ..services.tv_service import PHILIPS_AVAILABLE

    if not PHILIPS_AVAILABLE:
        return jsonify({'success': False, 'error': 'Philips TV support not available. Install: pip install philipstv'}), 400

    tv_ip = Config.get('tv_ip', current_app.config.get('TV_IP', ''))
    if not tv_ip:
        return jsonify({'success': False, 'error': 'TV IP-Adresse nicht konfiguriert. Bitte zuerst IP eingeben und speichern.'}), 400

    # Generate a unique request ID
    request_id = secrets.token_urlsafe(16)

    # Clean up old sessions (older than 5 minutes)
    current_time = time.time()
    with _philips_pairing_lock:
        for rid in list(_philips_pairing_sessions.keys()):
            if current_time - _philips_pairing_sessions[rid].get('created', 0) > 300:
                del _philips_pairing_sessions[rid]

        # Create session with threading primitives
        _philips_pairing_sessions[request_id] = {
            'ip': tv_ip,
            'created': time.time(),
            'pin_event': threading.Event(),
            'pin_value': None,
            'result': None,
            'error': None,
            'started': False
        }

    def run_pairing():
        """Background thread to run pairing"""
        try:
            from philipstv import PhilipsTVRemote

            session = _philips_pairing_sessions.get(request_id)
            if not session:
                return

            session['started'] = True

            # Create remote and start pairing
            remote = PhilipsTVRemote.new(tv_ip)

            def pin_callback():
                """Called by philipstv when PIN is shown on TV"""
                session = _philips_pairing_sessions.get(request_id)
                if not session:
                    raise Exception("Session expired")

                # Wait for PIN to be submitted (max 120 seconds)
                if session['pin_event'].wait(timeout=120):
                    return session['pin_value']
                else:
                    raise Exception("PIN timeout")

            # This call shows the PIN on TV and blocks until pin_callback returns
            credentials = remote.pair(pin_callback)

            if credentials and len(credentials) == 2:
                session['result'] = credentials
            else:
                session['error'] = 'Ungültige Antwort vom TV'

        except Exception as e:
            session = _philips_pairing_sessions.get(request_id)
            if session:
                session['error'] = str(e)

    # Start pairing in background thread
    pairing_thread = threading.Thread(target=run_pairing, daemon=True)
    pairing_thread.start()

    # Wait briefly for the pairing to start and PIN to appear on TV
    time.sleep(1.5)

    session = _philips_pairing_sessions.get(request_id)
    if session and session.get('error'):
        error = session['error']
        with _philips_pairing_lock:
            del _philips_pairing_sessions[request_id]
        return jsonify({'success': False, 'error': f'Pairing fehlgeschlagen: {error}'}), 500

    log_event(
        level='INFO',
        category='config',
        message='Philips TV pairing gestartet',
        details={'ip': tv_ip},
        source='manual'
    )

    return jsonify({
        'success': True,
        'request_id': request_id,
        'message': 'PIN wird auf dem TV angezeigt'
    })


@settings_bp.route('/pair/philips/complete', methods=['POST'])
@login_required
def pair_philips_complete():
    """Complete Philips TV pairing with PIN"""
    data = request.get_json()
    pin = data.get('pin')
    request_id = data.get('request_id')

    if not pin or not request_id:
        return jsonify({'success': False, 'error': 'PIN und Request-ID erforderlich'}), 400

    with _philips_pairing_lock:
        if request_id not in _philips_pairing_sessions:
            return jsonify({'success': False, 'error': 'Pairing-Sitzung abgelaufen. Bitte erneut starten.'}), 400

        session = _philips_pairing_sessions[request_id]
        tv_ip = session['ip']

        # Send PIN to the waiting background thread
        session['pin_value'] = pin
        session['pin_event'].set()

    # Wait for pairing to complete (max 10 seconds)
    for _ in range(20):
        time.sleep(0.5)
        session = _philips_pairing_sessions.get(request_id)
        if not session:
            return jsonify({'success': False, 'error': 'Session abgelaufen'}), 400

        if session.get('result'):
            philips_id, philips_key = session['result']

            # Store credentials in database
            Config.set('philips_id', philips_id)
            Config.set('philips_key', philips_key)

            # Reinitialize TV service with new credentials
            reinit_tv_service()

            # Clean up
            with _philips_pairing_lock:
                if request_id in _philips_pairing_sessions:
                    del _philips_pairing_sessions[request_id]

            log_event(
                level='INFO',
                category='config',
                message='Philips TV pairing erfolgreich',
                details={'ip': tv_ip},
                source='manual'
            )

            return jsonify({'success': True, 'message': 'Pairing erfolgreich!'})

        if session.get('error'):
            error = session['error']
            with _philips_pairing_lock:
                if request_id in _philips_pairing_sessions:
                    del _philips_pairing_sessions[request_id]

            log_event(
                level='ERROR',
                category='config',
                message='Philips TV pairing fehlgeschlagen',
                details={'error': error},
                source='manual'
            )
            return jsonify({'success': False, 'error': f'Pairing fehlgeschlagen: {error}'}), 500

    # Timeout
    with _philips_pairing_lock:
        if request_id in _philips_pairing_sessions:
            del _philips_pairing_sessions[request_id]

    return jsonify({'success': False, 'error': 'Pairing timeout - bitte erneut versuchen'}), 500


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


@settings_bp.route('/tv/diagnostics')
@login_required
def tv_diagnostics():
    """Fetch all available TV information for diagnostics"""
    from datetime import datetime
    from ..services.tv_service import get_current_tv_type

    tv = get_tv_service()
    tv_type = get_current_tv_type()

    result = {
        'success': False,
        'reachable': False,
        'paired': tv.is_paired,
        'tv_type': tv_type,
        'config': {
            'ip': Config.get('tv_ip', current_app.config.get('TV_IP', '')),
            'mac': Config.get('tv_mac', current_app.config.get('TV_MAC', '')),
            'tv_type': tv_type,
            'has_token': tv.is_paired
        },
        'ping': {},
        'api_response': None,
        'parsed_info': None,
        'volume': {},
        'apps': None,
        'philips_features': None,
        'error': None
    }

    # Test ping
    try:
        ping_result = tv.ping(timeout=2.0)
        result['ping'] = {'reachable': ping_result, 'timeout': 2.0}
        result['reachable'] = ping_result
    except Exception as e:
        result['ping'] = {'reachable': False, 'error': str(e)}

    if result['reachable']:
        # Get parsed info (works for both TV types)
        try:
            info = tv.get_info()
            if info:
                result['success'] = True
                result['parsed_info'] = {
                    'name': info.name,
                    'model': info.model,
                    'model_name': getattr(info, 'model_name', None),
                    'ip': info.ip,
                    'mac': info.mac,
                    'power_state': info.power_state,
                    'firmware': getattr(info, 'firmware', None),
                    'os': getattr(info, 'os', None),
                    'resolution': getattr(info, 'resolution', None),
                    'uuid': getattr(info, 'uuid', None)
                }
        except Exception as e:
            result['error'] = f'Info-Fehler: {str(e)}'

        # Get volume info
        try:
            volume = tv.get_volume()
            muted = getattr(tv, 'get_mute_status', lambda: None)()
            result['volume'] = {
                'available': volume is not None,
                'volume': volume,
                'muted': muted
            }
        except Exception as e:
            result['volume'] = {'available': False, 'error': str(e)}

        # TV-type specific diagnostics
        if tv_type == 'samsung':
            # Samsung: Get raw API response
            try:
                if hasattr(tv, '_rest_request'):
                    raw_data = tv._rest_request("", port=8001)
                    if raw_data is None:
                        raw_data = tv._rest_request("", port=getattr(tv, 'port', 8002))
                    if raw_data:
                        result['api_response'] = raw_data

                    # Try to get installed apps list
                    apps_data = tv._rest_request("applications", port=8001)
                    if apps_data:
                        result['apps'] = apps_data
            except Exception as e:
                if not result['error']:
                    result['error'] = f'Samsung API-Fehler: {str(e)}'

        elif tv_type == 'philips':
            # Philips: Get Philips-specific features
            try:
                philips_info = {}

                # Get applications
                if hasattr(tv, 'get_applications'):
                    apps = tv.get_applications()
                    if apps:
                        result['apps'] = apps

                # Get Ambilight status
                if hasattr(tv, 'get_ambilight_power'):
                    ambilight = tv.get_ambilight_power()
                    philips_info['ambilight'] = ambilight

                if philips_info:
                    result['philips_features'] = philips_info

            except Exception as e:
                if not result['error']:
                    result['error'] = f'Philips-Fehler: {str(e)}'

        if not result['error'] and result['parsed_info']:
            result['success'] = True
    else:
        result['error'] = 'TV nicht erreichbar (Ping fehlgeschlagen)'

    # Return HTML for HTMX, JSON otherwise
    if request.headers.get('HX-Request'):
        return render_template('partials/tv_diagnostics.html', data=result, now=datetime.now())

    return jsonify(result)


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
