"""
Fernbedienungs-Views
"""
import threading
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required

from ..services.tv_service import get_tv_service, invalidate_status_cache, set_cached_power_state, get_cached_status
from ..services.logger import log_event

remote_bp = Blueprint('remote', __name__, url_prefix='/remote')


def _run_async(func, *args, **kwargs):
    """Run function in background thread for faster UI response."""
    from flask import current_app

    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                func(*args, **kwargs)
            except Exception as e:
                print(f"[Async] Task failed: {e}", flush=True)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _send_key_async(key: str, delay: float = 0.1):
    """Send key in background thread for faster UI response."""
    def _send():
        tv = get_tv_service()
        tv.send_key(key, delay=delay)
        log_event(
            level='INFO',
            category='action',
            message=f'Taste gesendet: {key}',
            details={'key': key, 'async': True},
            source='manual'
        )

    _run_async(_send)


@remote_bp.route('/')
@login_required
def index():
    """Fernbedienungs-Seite"""
    expert_mode = request.args.get('expert', '0') == '1'

    # Use cached TV status for fast page load
    status = get_cached_status()
    reachable = status['connected']
    power_state = status['power_state']
    in_transition = status.get('in_transition', False)
    transition_type = status.get('transition_type')

    # Check if TV has a token (needed to know which controls are available)
    tv = get_tv_service()
    tv_has_token = tv.is_paired

    return render_template(
        'remote.html',
        expert_mode=expert_mode,
        reachable=reachable,
        power_state=power_state,
        in_transition=in_transition,
        transition_type=transition_type,
        tv_has_token=tv_has_token
    )


@remote_bp.route('/send-key', methods=['POST'])
@remote_bp.route('/send-key/<key>', methods=['POST'])
@login_required
def send_key(key=None):
    """Taste an TV senden - async für schnelle UI-Reaktion"""
    # Accept key from URL path, query params, or form data
    if key is None:
        key = request.args.get('key') or request.form.get('key')
    if not key:
        return jsonify({'success': False, 'error': 'Keine Taste angegeben'}), 400

    # Use async mode for instant UI response (default)
    # Set sync=1 to wait for completion
    sync_mode = request.args.get('sync', '0') == '1' or request.form.get('sync', '0') == '1'

    if sync_mode:
        tv = get_tv_service()
        try:
            tv.send_key(key, delay=0.1)
            log_event(
                level='INFO',
                category='action',
                message=f'Taste gesendet: {key}',
                details={'key': key},
                source='manual'
            )
            return jsonify({'success': True, 'key': key})
        except Exception as e:
            log_event(
                level='ERROR',
                category='action',
                message=f'Fehler beim Senden der Taste: {key}',
                details={'key': key, 'error': str(e)},
                source='manual'
            )
            return jsonify({'success': False, 'error': str(e)}), 500
    else:
        # Async mode - return immediately, send in background
        _send_key_async(key)
        return jsonify({'success': True, 'key': key, 'async': True})


def _power_action_async(action: str):
    """Execute power action in background thread."""
    def _execute():
        tv = get_tv_service()
        if action == 'on':
            tv.power_on()
        else:
            tv.power_off()
    _run_async(_execute)


@remote_bp.route('/power', methods=['POST'])
@login_required
def power():
    """TV ein-/ausschalten"""
    from flask import render_template
    from ..models import TVState

    action = request.form.get('action', 'toggle')

    try:
        if action == 'on':
            # Set cache immediately, send command async
            set_cached_power_state('on')
            _power_action_async('on')
            message = 'TV eingeschaltet (Wake-on-LAN)'
        elif action == 'off':
            # Set cache immediately, send command async
            set_cached_power_state('standby')
            _power_action_async('off')
            message = 'TV ausgeschaltet'
        else:
            # Toggle based on current cached status (avoid blocking API call)
            tv = get_tv_service()
            status = get_cached_status()
            if status['power_state'] == 'on':
                set_cached_power_state('standby')
                _power_action_async('off')
                message = 'TV ausgeschaltet'
            else:
                set_cached_power_state('on')
                _power_action_async('on')
                message = 'TV eingeschaltet (Wake-on-LAN)'

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action},
            source='manual'
        )

        # If HTMX request, return transition state HTML immediately
        # Don't call get_cached_status() here - it would check API and might
        # clear the transition before the UI even sees it. Let polling handle confirmation.
        if request.headers.get('HX-Request'):
            tv_state = TVState.get_instance()
            # Return the transition state we just set up
            if action == 'on' or (action == 'toggle' and message.startswith('TV eingeschaltet')):
                return render_template(
                    'partials/tv_status.html',
                    power_state='turning_on',
                    reachable=False,
                    in_transition=True,
                    transition_type='turning_on',
                    just_confirmed=False,
                    tv_state=tv_state,
                    tv_info=None
                )
            else:
                return render_template(
                    'partials/tv_status.html',
                    power_state='turning_off',
                    reachable=False,
                    in_transition=True,
                    transition_type='turning_off',
                    just_confirmed=False,
                    tv_state=tv_state,
                    tv_info=None
                )

        return jsonify({'success': True, 'message': message})
    except Exception as e:
        log_event(
            level='ERROR',
            category='action',
            message=f'Fehler bei Power-Aktion: {action}',
            details={'action': action, 'error': str(e)},
            source='manual'
        )
        return jsonify({'success': False, 'error': str(e)}), 500


def _volume_key_async(action: str, steps: int = 1):
    """Volume up/down/mute via keys in background thread."""
    def _change():
        tv = get_tv_service()
        if action == 'up':
            tv.volume_up(steps)
            message = f'Lautstärke +{steps}'
        elif action == 'down':
            tv.volume_down(steps)
            message = f'Lautstärke -{steps}'
        elif action == 'mute':
            tv.mute()
            message = 'Stumm umgeschaltet'
        else:
            return

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action, 'steps': steps, 'async': True},
            source='manual'
        )

    _run_async(_change)


@remote_bp.route('/volume', methods=['POST'])
@login_required
def volume():
    """Lautstärke ändern - UPnP für set/get (schnell), Keys async für up/down/mute"""
    action = request.form.get('action')  # 'up', 'down', 'mute', 'set', 'get'
    tv = get_tv_service()

    try:
        # Key-based actions: run async for fast UI
        if action in ('up', 'down', 'mute'):
            steps = int(request.form.get('steps', 1))
            _volume_key_async(action, steps)
            if action == 'up':
                message = f'Lautstärke +{steps}'
            elif action == 'down':
                message = f'Lautstärke -{steps}'
            else:
                message = 'Stumm umgeschaltet'
            return jsonify({'success': True, 'message': message, 'async': True})
        elif action == 'set':
            # Direct volume setting via UPnP
            value = int(request.form.get('value', 20))
            value = max(0, min(100, value))
            if tv.set_volume(value):
                message = f'Lautstärke auf {value} gesetzt'
            else:
                return jsonify({'success': False, 'error': 'UPnP nicht verfügbar'}), 503
        elif action == 'get':
            # Get current volume via UPnP
            current = tv.get_volume()
            muted = tv.get_mute_status()
            if current is not None:
                return jsonify({'success': True, 'volume': current, 'muted': muted})
            else:
                return jsonify({'success': False, 'error': 'UPnP nicht verfügbar'}), 503
        else:
            return jsonify({'success': False, 'error': 'Ungültige Aktion'}), 400

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action, 'value': request.form.get('value') or request.form.get('steps')},
            source='manual'
        )
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _channel_async(action: str, channel_num: str = None):
    """Change channel in background thread."""
    def _change():
        tv = get_tv_service()
        if action == 'up':
            tv.channel_up()
            message = 'Kanal +'
        elif action == 'down':
            tv.channel_down()
            message = 'Kanal -'
        elif action == 'set' and channel_num:
            tv.channel(int(channel_num))
            message = f'Kanal {channel_num}'
        else:
            return

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action, 'channel': channel_num, 'async': True},
            source='manual'
        )

    _run_async(_change)


@remote_bp.route('/channel', methods=['POST'])
@login_required
def channel():
    """Kanal wechseln - async für schnelle UI"""
    action = request.form.get('action')  # 'up', 'down', 'set'
    channel_num = request.form.get('channel')

    if action not in ('up', 'down', 'set'):
        return jsonify({'success': False, 'error': 'Ungültige Aktion'}), 400

    if action == 'set' and not channel_num:
        return jsonify({'success': False, 'error': 'Keine Kanalnummer angegeben'}), 400

    # Run async for instant UI response
    _channel_async(action, channel_num)

    message = 'Kanal +' if action == 'up' else 'Kanal -' if action == 'down' else f'Kanal {channel_num}'
    return jsonify({'success': True, 'message': message, 'async': True})


def _send_text_async(text: str):
    """Send text in background thread."""
    def _send():
        tv = get_tv_service()
        tv.send_text(text)
        log_event(
            level='INFO',
            category='action',
            message=f'Text gesendet: {text[:20]}...' if len(text) > 20 else f'Text gesendet: {text}',
            details={'text_length': len(text), 'async': True},
            source='manual'
        )

    _run_async(_send)


@remote_bp.route('/text', methods=['POST'])
@login_required
def send_text():
    """Text an TV senden - async für schnelle UI"""
    text = request.form.get('text', '')
    if not text:
        return jsonify({'success': False, 'error': 'Kein Text angegeben'}), 400

    _send_text_async(text)
    return jsonify({'success': True, 'message': 'Text gesendet', 'async': True})


@remote_bp.route('/app', methods=['POST'])
@login_required
def app_control():
    """App starten oder schließen"""
    action = request.form.get('action')  # 'run', 'close', 'status'
    app_id = request.form.get('app_id', '')

    if not app_id:
        return jsonify({'success': False, 'error': 'Keine App-ID angegeben'}), 400

    tv = get_tv_service()

    try:
        if action == 'run':
            if tv.run_app(app_id):
                message = f'App gestartet: {app_id}'
            else:
                return jsonify({'success': False, 'error': 'App konnte nicht gestartet werden'}), 500
        elif action == 'close':
            if tv.close_app(app_id):
                message = f'App geschlossen: {app_id}'
            else:
                return jsonify({'success': False, 'error': 'App konnte nicht geschlossen werden'}), 500
        elif action == 'status':
            status = tv.get_app_status(app_id)
            return jsonify({'success': True, 'status': status})
        else:
            return jsonify({'success': False, 'error': 'Ungültige Aktion'}), 400

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action, 'app_id': app_id},
            source='manual'
        )
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _hold_key_async(key: str, seconds: float):
    """Hold key in background thread."""
    def _hold():
        tv = get_tv_service()
        tv.hold_key(key, seconds)
        log_event(
            level='INFO',
            category='action',
            message=f'Taste gehalten: {key} ({seconds}s)',
            details={'key': key, 'seconds': seconds, 'async': True},
            source='manual'
        )

    _run_async(_hold)


@remote_bp.route('/hold-key', methods=['POST'])
@login_required
def hold_key():
    """Taste gedrückt halten - async für schnelle UI"""
    key = request.form.get('key')
    seconds = float(request.form.get('seconds', 1.0))

    if not key:
        return jsonify({'success': False, 'error': 'Keine Taste angegeben'}), 400

    seconds = max(0.1, min(5.0, seconds))  # Limit to 0.1-5 seconds
    _hold_key_async(key, seconds)
    return jsonify({'success': True, 'message': f'Taste {key} für {seconds}s gehalten', 'async': True})
