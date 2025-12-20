"""
Fernbedienungs-Views
"""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required

from ..models import Scenario
from ..services.tv_service import get_tv_service, invalidate_status_cache, get_cached_status
from ..services.logger import log_event

remote_bp = Blueprint('remote', __name__, url_prefix='/remote')


@remote_bp.route('/')
@login_required
def index():
    """Fernbedienungs-Seite"""
    scenarios = Scenario.query.all()
    expert_mode = request.args.get('expert', '0') == '1'

    # Use cached TV status for fast page load
    status = get_cached_status()
    reachable = status['connected']
    power_state = status['power_state']

    return render_template(
        'remote.html',
        scenarios=scenarios,
        expert_mode=expert_mode,
        reachable=reachable,
        power_state=power_state
    )


@remote_bp.route('/send-key', methods=['POST'])
@remote_bp.route('/send-key/<key>', methods=['POST'])
@login_required
def send_key(key=None):
    """Taste an TV senden"""
    # Accept key from URL path, query params, or form data
    if key is None:
        key = request.args.get('key') or request.form.get('key')
    if not key:
        return jsonify({'success': False, 'error': 'Keine Taste angegeben'}), 400

    tv = get_tv_service()

    try:
        tv.send_key(key)
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


@remote_bp.route('/power', methods=['POST'])
@login_required
def power():
    """TV ein-/ausschalten"""
    action = request.form.get('action', 'toggle')
    tv = get_tv_service()

    try:
        if action == 'on':
            tv.power_on()
            message = 'TV eingeschaltet (Wake-on-LAN)'
        elif action == 'off':
            tv.power_off()
            message = 'TV ausgeschaltet'
        else:
            # Toggle basierend auf aktuellem Status
            info = tv.get_info()
            if info and info.power_state == 'on':
                tv.power_off()
                message = 'TV ausgeschaltet'
            else:
                tv.power_on()
                message = 'TV eingeschaltet (Wake-on-LAN)'

        # Invalidate cache so next page load gets fresh status
        invalidate_status_cache()

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action},
            source='manual'
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


@remote_bp.route('/volume', methods=['POST'])
@login_required
def volume():
    """Lautstärke ändern"""
    action = request.form.get('action')  # 'up', 'down', 'mute'
    steps = int(request.form.get('steps', 1))
    tv = get_tv_service()

    try:
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
            return jsonify({'success': False, 'error': 'Ungültige Aktion'}), 400

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action, 'steps': steps},
            source='manual'
        )
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@remote_bp.route('/channel', methods=['POST'])
@login_required
def channel():
    """Kanal wechseln"""
    action = request.form.get('action')  # 'up', 'down', 'set'
    channel_num = request.form.get('channel')
    tv = get_tv_service()

    try:
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
            return jsonify({'success': False, 'error': 'Ungültige Aktion'}), 400

        log_event(
            level='INFO',
            category='action',
            message=message,
            details={'action': action, 'channel': channel_num},
            source='manual'
        )
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@remote_bp.route('/scenario/<int:scenario_id>', methods=['POST'])
@login_required
def run_scenario(scenario_id: int):
    """Szenario ausführen"""
    from ..services.scheduler import execute_scenario

    scenario = Scenario.query.get_or_404(scenario_id)

    try:
        execute_scenario(scenario)
        log_event(
            level='INFO',
            category='action',
            message=f'Szenario ausgeführt: {scenario.name}',
            details={'scenario_id': scenario_id, 'scenario_name': scenario.name},
            source='manual'
        )
        return jsonify({'success': True, 'message': f'Szenario "{scenario.name}" gestartet'})
    except Exception as e:
        log_event(
            level='ERROR',
            category='action',
            message=f'Fehler bei Szenario: {scenario.name}',
            details={'scenario_id': scenario_id, 'error': str(e)},
            source='manual'
        )
        return jsonify({'success': False, 'error': str(e)}), 500
