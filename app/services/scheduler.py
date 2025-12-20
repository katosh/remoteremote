"""
Scheduler-Service für geplante Aktionen
"""
import random
import time
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import pytz

# Globale Scheduler-Instanz
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Scheduler-Instanz abrufen"""
    return _scheduler


def init_scheduler(app):
    """Scheduler initialisieren und starten"""
    global _scheduler
    from .logger import log_event

    timezone = pytz.timezone(app.config.get('TIMEZONE', 'Europe/Berlin'))

    _scheduler = BackgroundScheduler(timezone=timezone)
    _scheduler.start()

    # Bestehende Zeitpläne laden
    with app.app_context():
        _load_schedules(app)

        # Log scheduler initialization
        jobs = _scheduler.get_jobs()
        log_event(
            level='INFO',
            category='system',
            message=f'Scheduler initialisiert mit {len(jobs)} Jobs',
            details={'jobs': [j.id for j in jobs]},
            source='system'
        )

    # Tägliche Log-Bereinigung
    _scheduler.add_job(
        func=_cleanup_logs_job,
        trigger='cron',
        hour=3,
        minute=0,
        id='cleanup_logs',
        replace_existing=True,
        kwargs={'app': app}
    )

    return _scheduler


def shutdown_scheduler():
    """Scheduler beenden"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None


def _load_schedules(app):
    """Alle aktiven Zeitpläne aus der Datenbank laden"""
    from ..models import Schedule

    schedules = Schedule.query.filter_by(enabled=True).all()

    for schedule in schedules:
        add_schedule(schedule, app)


def add_schedule(schedule, app=None):
    """Zeitplan zum Scheduler hinzufügen"""
    if not _scheduler:
        return

    job_id = f'schedule_{schedule.id}'

    # Bestehenden Job entfernen falls vorhanden
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if not schedule.enabled:
        return

    # Trigger erstellen
    if schedule.cron_expression:
        trigger = CronTrigger.from_crontab(
            schedule.cron_expression,
            timezone=_scheduler.timezone
        )
    elif schedule.next_run:
        trigger = DateTrigger(
            run_date=schedule.next_run,
            timezone=_scheduler.timezone
        )
    else:
        return

    # App-Kontext für den Job
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    job = _scheduler.add_job(
        func=_execute_schedule_job,
        trigger=trigger,
        id=job_id,
        replace_existing=True,
        kwargs={'schedule_id': schedule.id, 'app': app}
    )

    # Log job registration
    next_run = job.next_run_time.strftime('%d.%m.%Y %H:%M:%S') if job.next_run_time else 'unbekannt'
    print(f"[Scheduler] Job '{job_id}' registriert - Nächste Ausführung: {next_run}", flush=True)


def update_schedule(schedule, app=None):
    """Zeitplan im Scheduler aktualisieren"""
    remove_schedule(schedule.id)
    add_schedule(schedule, app)


def remove_schedule(schedule_id: int):
    """Zeitplan aus dem Scheduler entfernen"""
    if not _scheduler:
        return

    job_id = f'schedule_{schedule_id}'
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)


def calculate_next_run(cron_expression: str) -> Optional[datetime]:
    """Nächste Ausführungszeit berechnen"""
    if not cron_expression:
        return None

    try:
        trigger = CronTrigger.from_crontab(cron_expression)
        return trigger.get_next_fire_time(None, datetime.now())
    except Exception:
        return None


def _execute_schedule_job(schedule_id: int, app):
    """Job-Wrapper für Zeitplan-Ausführung"""
    print(f"[Scheduler] Führe Job 'schedule_{schedule_id}' aus...", flush=True)
    with app.app_context():
        from ..models import Schedule

        schedule = Schedule.query.get(schedule_id)
        if schedule and schedule.enabled:
            print(f"[Scheduler] Starte Zeitplan: {schedule.name}", flush=True)
            execute_schedule(schedule)
        else:
            print(f"[Scheduler] Zeitplan {schedule_id} nicht gefunden oder deaktiviert", flush=True)


def execute_schedule(schedule):
    """Zeitplan ausführen"""
    from ..models import db
    from .logger import log_event

    try:
        action_data = schedule.get_action_data()

        if schedule.action_type == 'startup':
            _execute_startup_action(action_data)
        elif schedule.action_type == 'key':
            _execute_key_action(action_data)
        elif schedule.action_type == 'power':
            _execute_power_action(action_data)
        elif schedule.action_type == 'sequence':
            _execute_sequence_action(action_data)
        elif schedule.action_type == 'scenario':
            _execute_scenario_action(action_data)

        schedule.last_run = datetime.utcnow()
        schedule.last_result = 'success'

        # Nächste Ausführungszeit aktualisieren
        if schedule.cron_expression:
            schedule.next_run = calculate_next_run(schedule.cron_expression)
        else:
            # Einmalige Ausführung - deaktivieren
            schedule.enabled = False
            schedule.next_run = None

        db.session.commit()

        log_event(
            level='INFO',
            category='schedule',
            message=f'Zeitplan ausgeführt: {schedule.name}',
            details={'schedule_id': schedule.id, 'action_type': schedule.action_type},
            source='schedule'
        )

    except Exception as e:
        schedule.last_run = datetime.utcnow()
        schedule.last_result = f'error: {str(e)}'
        db.session.commit()

        log_event(
            level='ERROR',
            category='schedule',
            message=f'Fehler bei Zeitplan: {schedule.name}',
            details={'schedule_id': schedule.id, 'error': str(e)},
            source='schedule'
        )


def _execute_key_action(action_data: dict):
    """Einzelne Taste senden"""
    from .tv_service import get_tv_service

    key = action_data.get('key')
    if key:
        tv = get_tv_service()
        tv.send_key(key)


def _execute_power_action(action_data: dict):
    """Power on (Wake-on-LAN) oder Power off ausführen"""
    from .tv_service import get_tv_service, set_cached_power_state

    action = action_data.get('action', 'on')
    tv = get_tv_service()

    if action == 'on':
        # Wake-on-LAN - funktioniert ohne Token
        tv.power_on()
        set_cached_power_state('on')
    elif action == 'off':
        tv.power_off()
        set_cached_power_state('standby')


def _execute_startup_action(action_data: dict):
    """
    TV einschalten und optional Kanal und Lautstärke setzen.
    Wartet nach dem Einschalten, bis TV bereit ist.
    """
    from .tv_service import get_tv_service, set_cached_power_state
    from .logger import log_event

    tv = get_tv_service()
    wait_time = action_data.get('wait', 15)
    channel = action_data.get('channel')
    volume = action_data.get('volume')

    # 1. TV einschalten (Wake-on-LAN)
    print(f"[Startup] Schalte TV ein...", flush=True)
    tv.power_on()
    set_cached_power_state('on')

    # 2. Warten bis TV bereit ist
    print(f"[Startup] Warte {wait_time}s bis TV bereit ist...", flush=True)
    time.sleep(wait_time)

    # 3. Optional: Lautstärke setzen (via UPnP - schnell)
    if volume is not None:
        print(f"[Startup] Setze Lautstärke auf {volume}%...", flush=True)
        try:
            tv.set_volume(volume)
        except Exception as e:
            log_event(
                level='WARNING',
                category='schedule',
                message=f'Lautstärke konnte nicht gesetzt werden: {e}',
                details={'volume': volume, 'error': str(e)},
                source='schedule'
            )

    # 4. Optional: Kanal wechseln
    if channel is not None:
        print(f"[Startup] Wechsle zu Kanal {channel}...", flush=True)
        try:
            tv.channel(channel)
        except Exception as e:
            log_event(
                level='WARNING',
                category='schedule',
                message=f'Kanal konnte nicht gewechselt werden: {e}',
                details={'channel': channel, 'error': str(e)},
                source='schedule'
            )

    print(f"[Startup] Fertig.", flush=True)


def _execute_sequence_action(action_data: dict):
    """Tastensequenz senden"""
    from .tv_service import get_tv_service

    keys = action_data.get('keys', [])
    delay = action_data.get('delay', 0.3)

    tv = get_tv_service()
    for key in keys:
        tv.send_key(key)
        time.sleep(delay)


def _execute_scenario_action(action_data: dict):
    """Szenario ausführen"""
    from ..models import Scenario

    scenario_id = action_data.get('scenario_id')
    if scenario_id:
        scenario = Scenario.query.get(scenario_id)
        if scenario:
            execute_scenario(scenario)


def execute_scenario(scenario):
    """
    Szenario mit allen Schritten ausführen.
    Unterstützt zufällige Verzögerungen für natürliches Verhalten.
    """
    from .tv_service import get_tv_service
    from .logger import log_event

    tv = get_tv_service()
    steps = scenario.get_steps()

    for step in steps:
        action = step.get('action')
        delay = step.get('delay', 0)

        # Zufällige Verzögerung wenn aktiviert
        if scenario.randomize_delays and delay > 0:
            min_delay = max(scenario.min_delay_ms, delay * 0.5)
            max_delay = min(scenario.max_delay_ms, delay * 1.5)
            delay = random.randint(int(min_delay), int(max_delay))

        # Aktion ausführen
        try:
            if action == 'key':
                key = step.get('key')
                tv.send_key(key)
            elif action == 'power_on':
                tv.power_on()
            elif action == 'power_off':
                tv.power_off()
            elif action == 'channel':
                channel = step.get('channel')
                tv.channel(channel)
            elif action == 'volume':
                level = step.get('level')
                # Volume auf bestimmtes Level setzen (geschätzt)
                # Da wir kein Feedback haben, senden wir entsprechend viele Up/Down
                pass  # TODO: Implementieren wenn Volume-Tracking vorhanden
            elif action == 'mute':
                tv.mute()
            elif action == 'wait':
                pass  # Nur warten

        except Exception as e:
            log_event(
                level='WARNING',
                category='action',
                message=f'Fehler bei Szenario-Schritt: {action}',
                details={'scenario': scenario.name, 'step': step, 'error': str(e)},
                source='schedule'
            )

        # Verzögerung vor nächstem Schritt
        if delay > 0:
            time.sleep(delay / 1000)  # Delay ist in ms


def _cleanup_logs_job(app):
    """Job für tägliche Log-Bereinigung"""
    with app.app_context():
        from .logger import cleanup_old_logs
        cleanup_old_logs()
