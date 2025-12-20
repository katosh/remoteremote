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
    from ..services.tv_service import get_cached_status

    mini = request.args.get('mini') == '1'
    tv_state = TVState.get_instance()

    # Use cached status for fast response
    cached = get_cached_status()
    power_state = cached['power_state']
    reachable = cached['connected']

    # HTMX erwartet HTML, normale Requests bekommen JSON
    if request.headers.get('HX-Request'):
        if mini:
            # Mini status for remote view
            return f'''<div class="flex items-center gap-3">
                <div class="w-3 h-3 rounded-full { 'bg-green-500' if reachable else 'bg-red-500' }"></div>
                <span class="text-sm">{ 'Verbunden' if reachable else 'Nicht verbunden' }</span>
            </div>'''
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
    """Nächste geplante Aktionen (für Dashboard - nur aktive)"""
    schedules = Schedule.query.filter(
        Schedule.enabled == True,
        Schedule.next_run != None
    ).order_by(Schedule.next_run).limit(5).all()

    if request.headers.get('HX-Request'):
        return render_template('partials/schedule_list.html', schedules=schedules, compact=True)

    return jsonify({
        'schedules': [{
            'id': s.id,
            'name': s.name,
            'next_run': s.next_run.isoformat() if s.next_run else None,
            'action_type': s.action_type
        } for s in schedules]
    })


@api_bp.route('/schedules/all')
@login_required
def all_schedules():
    """Alle Zeitpläne (für Zeitplan-Seite - aktive und inaktive)"""
    # Show enabled first (sorted by next_run), then disabled
    enabled = Schedule.query.filter(Schedule.enabled == True).order_by(Schedule.next_run).all()
    disabled = Schedule.query.filter(Schedule.enabled == False).order_by(Schedule.name).all()
    schedules = enabled + disabled

    if request.headers.get('HX-Request'):
        return render_template('partials/schedule_list.html', schedules=schedules, compact=False)

    return jsonify({
        'schedules': [{
            'id': s.id,
            'name': s.name,
            'enabled': s.enabled,
            'next_run': s.next_run.isoformat() if s.next_run else None,
            'action_type': s.action_type
        } for s in schedules]
    })


@api_bp.route('/logs/recent')
@login_required
def recent_logs():
    """Letzte Log-Einträge (für HTMX)"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    category = request.args.get('category', '')
    level = request.args.get('level', '')
    search = request.args.get('search', '')

    # Limit max entries per request
    limit = min(limit, 100)

    query = Log.query

    if category:
        query = query.filter(Log.category == category)
    if level:
        query = query.filter(Log.level == level)
    if search:
        query = query.filter(Log.message.ilike(f'%{search}%'))

    logs = query.order_by(Log.timestamp.desc()).offset(offset).limit(limit).all()

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
