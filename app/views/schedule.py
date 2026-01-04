"""
Schedule Views
"""
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from flask_babel import gettext as _
import pytz

from ..models import db, Schedule, Config
from ..services.logger import log_event
from ..services.scheduler import calculate_next_run, add_schedule, update_schedule, remove_schedule

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


def get_tv_timezone_info():
    """Get current timezone and time for display."""
    tz_name = Config.get('timezone') or 'Europe/Berlin'
    try:
        tz = pytz.timezone(tz_name)
        current_time = datetime.now(tz)
        return {
            'name': tz_name,
            'current_time_iso': current_time.isoformat(),
            'current_time': current_time.strftime('%H:%M'),
            'current_date': current_time.strftime('%d.%m.%Y')
        }
    except Exception:
        now = datetime.now()
        return {
            'name': tz_name,
            'current_time_iso': now.isoformat(),
            'current_time': now.strftime('%H:%M'),
            'current_date': now.strftime('%d.%m.%Y')
        }


@schedule_bp.route('/')
@login_required
def index():
    """Schedule overview"""
    schedules = Schedule.query.order_by(Schedule.next_run).all()
    tz_info = get_tv_timezone_info()

    return render_template(
        'schedule.html',
        schedules=schedules,
        timezone_info=tz_info
    )


@schedule_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Neuen Zeitplan erstellen"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        action_type = request.form.get('action_type')  # 'power', 'key', 'sequence', 'scenario'

        # Build cron expression from simple mode or use custom
        cron_expression = request.form.get('cron_expression')
        if not cron_expression or cron_expression == '0 7 * * *':
            # Simple mode - build cron from hour/minute/repeat
            hour = request.form.get('hour', '7')
            minute = request.form.get('minute', '0')
            repeat = request.form.get('repeat', 'daily')

            if repeat == 'once':
                # For one-time, set next_run directly
                from datetime import timedelta
                tz_name = Config.get('timezone') or 'Europe/Berlin'
                tz = pytz.timezone(tz_name)
                now = datetime.now(tz)
                run_time = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
                if run_time <= now:
                    run_time += timedelta(days=1)
                next_run = run_time
                cron_expression = None
            elif repeat == 'daily':
                cron_expression = f"{minute} {hour} * * *"
            elif repeat == 'weekdays':
                cron_expression = f"{minute} {hour} * * 1-5"
            elif repeat == 'weekends':
                cron_expression = f"{minute} {hour} * * 0,6"
            elif repeat == 'weekly':
                weekdays = request.form.getlist('weekdays')
                days = ','.join(weekdays) if weekdays else '1'
                cron_expression = f"{minute} {hour} * * {days}"
            else:
                cron_expression = f"{minute} {hour} * * *"

        # Calculate next run for recurring schedules
        if cron_expression:
            next_run = calculate_next_run(cron_expression)
        elif 'next_run' not in locals():
            next_run = None

        # Aktionsdaten
        action_data = {}
        if action_type == 'startup':
            # Power on + optional channel + optional volume
            channel = request.form.get('startup_channel')
            volume = request.form.get('startup_volume')
            wait = request.form.get('startup_wait', '15')
            skip_if_on = request.form.get('startup_skip_if_on') == 'on'
            if channel:
                action_data['channel'] = int(channel)
            if volume:
                action_data['volume'] = int(volume)
            action_data['wait'] = int(wait)
            action_data['skip_if_on'] = skip_if_on
        elif action_type == 'power':
            action_data['action'] = request.form.get('power_action', 'on')
        elif action_type == 'key':
            action_data['key'] = request.form.get('key')
        elif action_type == 'sequence':
            keys_str = request.form.get('sequence_keys', '')
            action_data['keys'] = [k.strip() for k in keys_str.split(',') if k.strip()]
            action_data['delay'] = int(request.form.get('sequence_delay', 300)) / 1000
        elif action_type == 'scenario':
            action_data['scenario_id'] = int(request.form.get('scenario_id'))

        schedule = Schedule(
            name=name,
            description=description,
            cron_expression=cron_expression,
            next_run=next_run,
            action_type=action_type,
            enabled=True
        )
        schedule.set_action_data(action_data)

        db.session.add(schedule)
        db.session.commit()

        # Im Scheduler registrieren
        add_schedule(schedule)

        log_event(
            level='INFO',
            category='schedule',
            message=f'Zeitplan erstellt: {name}',
            details={'schedule_id': schedule.id, 'action_type': action_type},
            source='manual'
        )

        flash(f'Zeitplan "{name}" wurde erstellt.', 'success')
        return redirect(url_for('schedule.index'))

    return render_template('schedule_form.html', schedule=None)


@schedule_bp.route('/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(schedule_id: int):
    """Zeitplan bearbeiten"""
    schedule = Schedule.query.get_or_404(schedule_id)

    if request.method == 'POST':
        schedule.name = request.form.get('name')
        schedule.description = request.form.get('description', '')

        # Build cron expression from simple mode or use custom
        cron_expression = request.form.get('cron_expression')
        if not cron_expression or cron_expression == schedule.cron_expression:
            # Simple mode - build cron from hour/minute/repeat
            hour = request.form.get('hour', '7')
            minute = request.form.get('minute', '0')
            repeat = request.form.get('repeat', 'daily')

            if repeat == 'once':
                # For one-time, set next_run directly
                from datetime import timedelta
                tz_name = Config.get('timezone') or 'Europe/Berlin'
                tz = pytz.timezone(tz_name)
                now = datetime.now(tz)
                run_time = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
                if run_time <= now:
                    run_time += timedelta(days=1)
                schedule.next_run = run_time
                schedule.cron_expression = None
            elif repeat == 'daily':
                schedule.cron_expression = f"{minute} {hour} * * *"
            elif repeat == 'weekdays':
                schedule.cron_expression = f"{minute} {hour} * * 1-5"
            elif repeat == 'weekends':
                schedule.cron_expression = f"{minute} {hour} * * 0,6"
            elif repeat == 'weekly':
                weekdays = request.form.getlist('weekdays')
                days = ','.join(weekdays) if weekdays else '1'
                schedule.cron_expression = f"{minute} {hour} * * {days}"
            else:
                schedule.cron_expression = f"{minute} {hour} * * *"
        else:
            schedule.cron_expression = cron_expression

        # Calculate next run for recurring schedules
        if schedule.cron_expression:
            schedule.next_run = calculate_next_run(schedule.cron_expression)

        action_type = request.form.get('action_type')
        schedule.action_type = action_type

        action_data = {}
        if action_type == 'startup':
            channel = request.form.get('startup_channel')
            volume = request.form.get('startup_volume')
            wait = request.form.get('startup_wait', '15')
            skip_if_on = request.form.get('startup_skip_if_on') == 'on'
            if channel:
                action_data['channel'] = int(channel)
            if volume:
                action_data['volume'] = int(volume)
            action_data['wait'] = int(wait)
            action_data['skip_if_on'] = skip_if_on
        elif action_type == 'power':
            action_data['action'] = request.form.get('power_action', 'on')
        elif action_type == 'key':
            action_data['key'] = request.form.get('key')
        elif action_type == 'sequence':
            keys_str = request.form.get('sequence_keys', '')
            action_data['keys'] = [k.strip() for k in keys_str.split(',') if k.strip()]
            action_data['delay'] = int(request.form.get('sequence_delay', 300)) / 1000
        elif action_type == 'scenario':
            action_data['scenario_id'] = int(request.form.get('scenario_id'))

        schedule.set_action_data(action_data)

        # Handle enabled toggle - check the value, not just presence (hidden input always exists)
        schedule.enabled = request.form.get('enabled') == 'on'

        db.session.commit()

        # Im Scheduler aktualisieren
        if schedule.enabled:
            update_schedule(schedule)
        else:
            remove_schedule(schedule.id)

        log_event(
            level='INFO',
            category='schedule',
            message=f'Zeitplan bearbeitet: {schedule.name}',
            details={'schedule_id': schedule.id},
            source='manual'
        )

        flash(f'Zeitplan "{schedule.name}" wurde aktualisiert.', 'success')
        return redirect(url_for('schedule.index'))

    return render_template('schedule_form.html', schedule=schedule)


@schedule_bp.route('/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete(schedule_id: int):
    """Zeitplan löschen"""
    schedule = Schedule.query.get_or_404(schedule_id)
    name = schedule.name

    # Aus Scheduler entfernen
    remove_schedule(schedule_id)

    db.session.delete(schedule)
    db.session.commit()

    log_event(
        level='INFO',
        category='schedule',
        message=f'Zeitplan gelöscht: {name}',
        details={'schedule_id': schedule_id},
        source='manual'
    )

    flash(f'Zeitplan "{name}" wurde gelöscht.', 'success')

    # For HTMX requests, use HX-Redirect header
    if request.headers.get('HX-Request'):
        response = jsonify({'success': True})
        response.headers['HX-Redirect'] = url_for('schedule.index')
        return response

    return redirect(url_for('schedule.index'))


@schedule_bp.route('/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle(schedule_id: int):
    """Zeitplan aktivieren/deaktivieren"""
    schedule = Schedule.query.get_or_404(schedule_id)
    schedule.enabled = not schedule.enabled
    db.session.commit()

    # Im Scheduler aktualisieren
    if schedule.enabled:
        add_schedule(schedule)
    else:
        remove_schedule(schedule_id)

    status = 'aktiviert' if schedule.enabled else 'deaktiviert'
    log_event(
        level='INFO',
        category='schedule',
        message=f'Zeitplan {status}: {schedule.name}',
        details={'schedule_id': schedule_id, 'enabled': schedule.enabled},
        source='manual'
    )

    # For HTMX requests, return the updated schedule list
    if request.headers.get('HX-Request'):
        enabled = Schedule.query.filter(Schedule.enabled == True).order_by(Schedule.next_run).all()
        disabled = Schedule.query.filter(Schedule.enabled == False).order_by(Schedule.name).all()
        schedules = enabled + disabled
        return render_template('partials/schedule_list.html', schedules=schedules, compact=False)

    return jsonify({'success': True, 'enabled': schedule.enabled})


@schedule_bp.route('/<int:schedule_id>/run', methods=['POST'])
@login_required
def run_now(schedule_id: int):
    """Zeitplan sofort ausführen"""
    from ..services.scheduler import execute_schedule

    schedule = Schedule.query.get_or_404(schedule_id)

    try:
        execute_schedule(schedule)
        log_event(
            level='INFO',
            category='schedule',
            message=f'Zeitplan manuell ausgeführt: {schedule.name}',
            details={'schedule_id': schedule_id},
            source='manual'
        )
        return jsonify({'success': True, 'message': f'"{schedule.name}" wurde ausgeführt.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
