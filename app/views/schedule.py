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
        schedule_type = request.form.get('schedule_type')  # 'once', 'recurring'
        action_type = request.form.get('action_type')  # 'key', 'sequence', 'scenario'

        # Zeitplan-Daten
        if schedule_type == 'once':
            run_datetime = request.form.get('run_datetime')
            next_run = datetime.fromisoformat(run_datetime) if run_datetime else None
            cron_expression = None
        else:
            cron_expression = request.form.get('cron_expression')
            next_run = calculate_next_run(cron_expression) if cron_expression else None

        # Aktionsdaten
        action_data = {}
        if action_type == 'key':
            action_data['key'] = request.form.get('action_key')
        elif action_type == 'sequence':
            keys = request.form.getlist('sequence_keys')
            action_data['keys'] = keys
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

        schedule_type = request.form.get('schedule_type')
        if schedule_type == 'once':
            run_datetime = request.form.get('run_datetime')
            schedule.next_run = datetime.fromisoformat(run_datetime) if run_datetime else None
            schedule.cron_expression = None
        else:
            schedule.cron_expression = request.form.get('cron_expression')
            schedule.next_run = calculate_next_run(schedule.cron_expression)

        action_type = request.form.get('action_type')
        schedule.action_type = action_type

        action_data = {}
        if action_type == 'key':
            action_data['key'] = request.form.get('action_key')
        elif action_type == 'sequence':
            keys = request.form.getlist('sequence_keys')
            action_data['keys'] = keys
        elif action_type == 'scenario':
            action_data['scenario_id'] = int(request.form.get('scenario_id'))

        schedule.set_action_data(action_data)
        db.session.commit()

        # Im Scheduler aktualisieren
        scheduler = get_scheduler()
        if scheduler:
            scheduler.update_schedule(schedule)

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
