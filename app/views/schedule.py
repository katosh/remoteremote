"""
Zeitplanungs-Views
"""
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required

from ..models import db, Schedule, Scenario
from ..services.logger import log_event
from ..services.scheduler import get_scheduler, calculate_next_run

schedule_bp = Blueprint('schedule', __name__, url_prefix='/schedule')


@schedule_bp.route('/')
@login_required
def index():
    """Zeitplan-Übersicht"""
    schedules = Schedule.query.order_by(Schedule.next_run).all()
    scenarios = Scenario.query.all()

    return render_template(
        'schedule.html',
        schedules=schedules,
        scenarios=scenarios
    )


@schedule_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Neuen Zeitplan erstellen"""
    scenarios = Scenario.query.all()

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
                import pytz
                tz = pytz.timezone('Europe/Berlin')
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
        if action_type == 'power':
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
        scheduler = get_scheduler()
        if scheduler:
            scheduler.add_schedule(schedule)

        log_event(
            level='INFO',
            category='schedule',
            message=f'Zeitplan erstellt: {name}',
            details={'schedule_id': schedule.id, 'action_type': action_type},
            source='manual'
        )

        flash(f'Zeitplan "{name}" wurde erstellt.', 'success')
        return redirect(url_for('schedule.index'))

    return render_template('schedule_form.html', schedule=None, scenarios=scenarios)


@schedule_bp.route('/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(schedule_id: int):
    """Zeitplan bearbeiten"""
    schedule = Schedule.query.get_or_404(schedule_id)
    scenarios = Scenario.query.all()

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
                import pytz
                tz = pytz.timezone('Europe/Berlin')
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
        if action_type == 'power':
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

        # Handle enabled toggle
        schedule.enabled = 'enabled' in request.form

        db.session.commit()

        # Im Scheduler aktualisieren
        scheduler = get_scheduler()
        if scheduler:
            if schedule.enabled:
                scheduler.update_schedule(schedule)
            else:
                scheduler.remove_schedule(schedule.id)

        log_event(
            level='INFO',
            category='schedule',
            message=f'Zeitplan bearbeitet: {schedule.name}',
            details={'schedule_id': schedule.id},
            source='manual'
        )

        flash(f'Zeitplan "{schedule.name}" wurde aktualisiert.', 'success')
        return redirect(url_for('schedule.index'))

    return render_template('schedule_form.html', schedule=schedule, scenarios=scenarios)


@schedule_bp.route('/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete(schedule_id: int):
    """Zeitplan löschen"""
    schedule = Schedule.query.get_or_404(schedule_id)
    name = schedule.name

    # Aus Scheduler entfernen
    scheduler = get_scheduler()
    if scheduler:
        scheduler.remove_schedule(schedule_id)

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
    scheduler = get_scheduler()
    if scheduler:
        if schedule.enabled:
            scheduler.add_schedule(schedule)
        else:
            scheduler.remove_schedule(schedule_id)

    status = 'aktiviert' if schedule.enabled else 'deaktiviert'
    log_event(
        level='INFO',
        category='schedule',
        message=f'Zeitplan {status}: {schedule.name}',
        details={'schedule_id': schedule_id, 'enabled': schedule.enabled},
        source='manual'
    )

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
