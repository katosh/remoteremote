"""
API-Endpoints für HTMX und JSON-Responses
"""
from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from ..models import TVState, Schedule, Log, db
from ..services.tv_service import get_tv_service

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/tv/status')
@login_required
def tv_status():
    """Aktueller TV-Status (für HTMX Polling)"""
    tv = get_tv_service()
    tv_state = TVState.get_instance()

    power_state = 'unknown'
    reachable = False

    try:
        info = tv.get_info()
        if info:
            power_state = info.power_state
            reachable = True
            tv_state.power_state = power_state
            tv_state.last_confirmed = db.func.now()
            db.session.commit()
    except Exception:
        pass

    # HTMX erwartet HTML, normale Requests bekommen JSON
    if request.headers.get('HX-Request'):
        return render_template(
            'partials/tv_status.html',
            power_state=power_state,
            reachable=reachable,
            tv_state=tv_state
        )

    return jsonify({
        'power_state': power_state,
        'reachable': reachable,
        'estimated_volume': tv_state.estimated_volume,
        'estimated_channel': tv_state.estimated_channel,
        'estimated_muted': tv_state.estimated_muted
    })


@api_bp.route('/tv/info')
@login_required
def tv_info():
    """Vollständige TV-Informationen"""
    tv = get_tv_service()

    try:
        info = tv.get_info()
        if info:
            return jsonify({
                'success': True,
                'info': {
                    'name': info.name,
                    'model': info.model_name,
                    'ip': info.ip,
                    'mac': info.mac,
                    'power_state': info.power_state,
                    'os': info.os,
                    'resolution': info.resolution
                }
            })
        return jsonify({'success': False, 'error': 'TV nicht erreichbar'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@api_bp.route('/schedules/upcoming')
@login_required
def upcoming_schedules():
    """Nächste geplante Aktionen (für HTMX)"""
    schedules = Schedule.query.filter(
        Schedule.enabled == True,
        Schedule.next_run != None
    ).order_by(Schedule.next_run).limit(5).all()

    if request.headers.get('HX-Request'):
        return render_template('partials/schedule_list.html', schedules=schedules)

    return jsonify({
        'schedules': [{
            'id': s.id,
            'name': s.name,
            'next_run': s.next_run.isoformat() if s.next_run else None,
            'action_type': s.action_type
        } for s in schedules]
    })


@api_bp.route('/logs/recent')
@login_required
def recent_logs():
    """Letzte Log-Einträge (für HTMX)"""
    limit = request.args.get('limit', 10, type=int)
    category = request.args.get('category', '')

    query = Log.query
    if category:
        query = query.filter(Log.category == category)

    logs = query.order_by(Log.timestamp.desc()).limit(limit).all()

    if request.headers.get('HX-Request'):
        return render_template('partials/log_entries.html', logs=logs)

    return jsonify({
        'logs': [{
            'id': log.id,
            'timestamp': log.timestamp.isoformat(),
            'level': log.level,
            'category': log.category,
            'message': log.message
        } for log in logs]
    })


@api_bp.route('/health')
def health():
    """Health-Check Endpoint"""
    tv = get_tv_service()
    tv_reachable = False

    try:
        info = tv.get_info()
        tv_reachable = info is not None
    except Exception:
        pass

    return jsonify({
        'status': 'ok',
        'tv_reachable': tv_reachable,
        'tv_paired': tv.is_paired
    })
