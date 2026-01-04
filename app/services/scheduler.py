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
_app_instance = None  # Store app reference for reloading


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Scheduler-Instanz abrufen"""
    return _scheduler


def get_configured_timezone():
    """Get timezone from database config, fallback to app config."""
    from flask import current_app
    from ..models import Config

    # Try database first
    tz_name = Config.get('timezone')
    if not tz_name:
        # Fallback to app config
        tz_name = current_app.config.get('TIMEZONE', 'Europe/Berlin')

    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone('Europe/Berlin')


def init_scheduler(app):
    """Scheduler initialisieren und starten"""
    global _scheduler, _app_instance
    from .logger import log_event

    _app_instance = app

    # Get timezone from database or config
    with app.app_context():
        timezone = get_configured_timezone()

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

    # Get current configured timezone (from database)
    timezone = get_configured_timezone()

    # Trigger erstellen
    if schedule.cron_expression:
        trigger = CronTrigger.from_crontab(
            schedule.cron_expression,
            timezone=timezone
        )
    elif schedule.next_run:
        trigger = DateTrigger(
            run_date=schedule.next_run,
            timezone=timezone
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


def reload_all_schedules():
    """Reload all schedules with current timezone. Call after timezone change."""
    global _app_instance
    from .logger import log_event

    if not _scheduler or not _app_instance:
        return

    with _app_instance.app_context():
        from ..models import Schedule

        # Get new timezone
        new_tz = get_configured_timezone()

        # Remove all schedule jobs (keep system jobs like cleanup_logs)
        for job in _scheduler.get_jobs():
            if job.id.startswith('schedule_'):
                _scheduler.remove_job(job.id)

        # Reload all enabled schedules with new timezone
        schedules = Schedule.query.filter_by(enabled=True).all()
        for schedule in schedules:
            add_schedule(schedule, _app_instance)

        log_event(
            level='INFO',
            category='system',
            message=f'Schedules reloaded with timezone: {new_tz}',
            details={'schedule_count': len(schedules)},
            source='system'
        )


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
        timezone = get_configured_timezone()
        trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone)
        now = datetime.now(timezone)
        return trigger.get_next_fire_time(None, now)
    except Exception:
        return None


def _execute_schedule_job(schedule_id: int, app):
    """Job-Wrapper für Zeitplan-Ausführung"""
    print(f"[Scheduler] Führe Job 'schedule_{schedule_id}' aus...", flush=True)
    with app.app_context():
        from ..models import Schedule, db

        schedule = db.session.get(Schedule, schedule_id)
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
        # Add schedule info for actions that need it (e.g., warning display)
        action_data['_schedule_id'] = schedule.id
        action_data['_schedule_name'] = schedule.name

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
            # Also sync with APScheduler job's actual next run time
            job = _scheduler.get_job(f'schedule_{schedule.id}') if _scheduler else None
            if job and job.next_run_time:
                schedule.next_run = job.next_run_time.replace(tzinfo=None)  # Store as naive UTC
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
    from .tv_service import get_tv_service, set_cached_power_state, reinit_tv_service
    from .logger import log_event

    action = action_data.get('action', 'on')

    # Reinitialize TV service to ensure fresh connection (important for scheduled tasks)
    reinit_tv_service()
    tv = get_tv_service()

    print(f"[Power Action] Executing power action: {action}", flush=True)

    if action == 'on':
        # Wake-on-LAN - funktioniert ohne Token
        # Log MAC address for debugging
        mac = getattr(tv, 'mac', None)
        print(f"[Power Action] Sending Wake-on-LAN to MAC: {mac or 'NOT SET'}", flush=True)
        if not mac:
            log_event(
                level='WARNING',
                category='schedule',
                message='No MAC address configured - WoL will fail',
                details={'action': action},
                source='schedule'
            )
        tv.power_on()
        set_cached_power_state('on')
        print(f"[Power Action] Power ON sent via Wake-on-LAN", flush=True)
    elif action == 'off':
        # Check if warning should be shown before shutdown
        show_warning = action_data.get('show_warning', False)
        warning_seconds = action_data.get('warning_seconds', 60)
        schedule_id = action_data.get('_schedule_id')

        if show_warning and schedule_id:
            # Show warning on TV and wait for user response
            # Run in background thread to avoid blocking gunicorn workers
            import threading
            from flask import current_app

            # Capture app for thread context
            app = current_app._get_current_object()

            def warning_then_shutdown():
                with app.app_context():
                    cancelled = _show_shutdown_warning(tv, schedule_id, warning_seconds)
                    if cancelled:
                        print(f"[Power Action] Shutdown cancelled by user", flush=True)
                        log_event(
                            level='INFO',
                            category='schedule',
                            message='Shutdown cancelled by user via TV warning',
                            details={'schedule_id': schedule_id},
                            source='schedule'
                        )
                        return
                    # Proceed with shutdown after warning
                    try:
                        tv.power_off()
                        set_cached_power_state('off')
                        print(f"[Power Action] Power OFF sent after warning", flush=True)
                    except Exception as e:
                        print(f"[Power Action] Power OFF failed: {e}", flush=True)

            thread = threading.Thread(target=warning_then_shutdown, daemon=True)
            thread.start()
            print(f"[Power Action] Warning started in background thread", flush=True)
            return  # Don't block - shutdown happens after warning in thread

        # Power off requires WebSocket connection
        if not tv.is_paired:
            print(f"[Power Action] WARNING: No token - power off may fail", flush=True)
        tv.power_off()
        set_cached_power_state('off')
        print(f"[Power Action] Power OFF sent", flush=True)
    else:
        print(f"[Power Action] Unknown action: {action}", flush=True)


def _get_server_url() -> str:
    """
    Get the server URL for the warning page.
    Tries config first, then auto-detects local IP.
    """
    from ..models import Config
    from flask import current_app
    import socket

    # First try user-configured URL
    server_url = Config.get('server_url')
    if server_url:
        return server_url

    # Auto-detect local IP address (not localhost)
    try:
        # Create a socket to determine which interface would be used to reach an external IP
        # This doesn't actually connect, just determines the route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        # Fallback: try to get any non-loopback IP
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            # If we got 127.x.x.x, try to find a better one
            if local_ip.startswith('127.'):
                # Last resort: scan interfaces
                for ip in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    addr = ip[4][0]
                    if not addr.startswith('127.'):
                        local_ip = addr
                        break
        except Exception:
            local_ip = '127.0.0.1'

    # Get port from config or default
    port = current_app.config.get('SERVER_PORT', 5000)

    return f'http://{local_ip}:{port}'


def _show_shutdown_warning(tv, schedule_id: int, warning_seconds: int) -> bool:
    """
    Show shutdown warning on TV and wait for user response.
    Returns True if shutdown was cancelled, False otherwise.

    Note: Even if the browser cannot be opened on the TV (some TVs don't support this),
    the warning period still runs and users can cancel via the web interface.
    """
    from flask import current_app
    from .warning_token import generate_warning_token, is_shutdown_cancelled, clear_cancellation
    from .logger import log_event
    from ..models import Config

    print(f"[Warning] Showing shutdown warning for {warning_seconds}s...", flush=True)

    browser_opened = False
    warning_url = None

    try:
        # Generate secure token for the warning page
        token = generate_warning_token(schedule_id, expires_in_seconds=warning_seconds + 30)

        # Build the warning URL
        server_url = _get_server_url()
        warning_url = f"{server_url}/schedule/warning/{token}"
        print(f"[Warning] Warning page URL: {warning_url}", flush=True)

        # Try to open the browser on the TV (best effort)
        tv_ip = getattr(tv, 'ip', None)
        print(f"[Warning] TV IP: {tv_ip}", flush=True)

        if not tv_ip:
            print(f"[Warning] TV IP is empty - cannot open browser", flush=True)
        elif hasattr(tv, 'open_browser'):
            # Try standard open_browser first (passes URL via API)
            try:
                result = tv.open_browser(warning_url)
                print(f"[Warning] open_browser result: {result}", flush=True)
                browser_opened = bool(result)
            except Exception as e:
                print(f"[Warning] open_browser failed: {e}", flush=True)

            # If browser opened but URL might not have been passed (2020+ Samsung TVs),
            # try the text input workaround
            if not browser_opened and hasattr(tv, 'open_browser_with_text'):
                try:
                    print(f"[Warning] Trying text input workaround...", flush=True)
                    result = tv.open_browser_with_text(warning_url, wait_time=3.0)
                    print(f"[Warning] open_browser_with_text result: {result}", flush=True)
                    browser_opened = bool(result)
                except Exception as e:
                    print(f"[Warning] open_browser_with_text failed: {e}", flush=True)
        else:
            print(f"[Warning] TV does not support opening browser", flush=True)

        if not browser_opened:
            # Log that browser couldn't be opened, but continue with warning period
            log_event(
                level='INFO',
                category='schedule',
                message='Browser could not be opened on TV - warning period still active via web interface',
                details={
                    'schedule_id': schedule_id,
                    'warning_url': warning_url,
                    'warning_seconds': warning_seconds
                },
                source='schedule'
            )
            print(f"[Warning] Browser not opened on TV - warning period still active", flush=True)
            print(f"[Warning] Cancel via web interface: {warning_url}", flush=True)

    except Exception as e:
        print(f"[Warning] Error preparing warning: {e}", flush=True)
        log_event(
            level='WARNING',
            category='schedule',
            message=f'Error preparing shutdown warning: {e}',
            details={'schedule_id': schedule_id, 'error': str(e)},
            source='schedule'
        )

    # Always wait for the warning period and check for cancellations
    # (even if browser couldn't be opened - user may cancel via web interface)
    check_interval = 2  # Check every 2 seconds
    elapsed = 0

    while elapsed < warning_seconds:
        time.sleep(check_interval)
        elapsed += check_interval

        # Check if user cancelled
        if is_shutdown_cancelled(schedule_id):
            clear_cancellation(schedule_id)
            print(f"[Warning] User cancelled shutdown!", flush=True)
            return True

    # Clear any stale cancellation data
    clear_cancellation(schedule_id)
    print(f"[Warning] Warning period expired - proceeding with shutdown", flush=True)
    return False


def _execute_startup_action(action_data: dict):
    """
    TV einschalten und optional Kanal und Lautstärke setzen.
    Wartet nach dem Einschalten, bis TV bereit ist.
    Supports both Samsung and Philips TVs.
    """
    from .tv_service import get_tv_service, set_cached_power_state, get_current_tv_type, reinit_tv_service
    from .logger import log_event

    # Reinitialize TV service to ensure fresh connection (important for scheduled tasks)
    reinit_tv_service()
    tv = get_tv_service()
    tv_type = get_current_tv_type()
    wait_time = action_data.get('wait', 15)
    channel = action_data.get('channel')
    volume = action_data.get('volume')
    skip_if_on = action_data.get('skip_if_on', False)

    # Check if TV is already on
    tv_already_on = False
    try:
        info = tv.get_info()
        if info and getattr(info, 'power_state', None) == 'on':
            tv_already_on = True
            print(f"[Startup] TV is already ON", flush=True)
    except Exception as e:
        print(f"[Startup] Could not check TV state: {e}", flush=True)

    # If skip_if_on is enabled and TV is already on, skip entire action
    if skip_if_on and tv_already_on:
        print(f"[Startup] Skipping - TV already on and skip_if_on is enabled", flush=True)
        log_event(
            level='INFO',
            category='schedule',
            message='Startup skipped - TV already on',
            details={'skip_if_on': True},
            source='schedule'
        )
        return

    # Only do power-on sequence if TV is not already on
    if not tv_already_on:
        # 1. TV einschalten (Wake-on-LAN) - use close_menu=True for Samsung to exit Smart Hub
        mac = getattr(tv, 'mac', None)
        print(f"[Startup] Schalte TV ein ({tv_type}), MAC: {mac or 'NOT SET'}...", flush=True)
        if not mac:
            log_event(
                level='WARNING',
                category='schedule',
                message='No MAC address configured - WoL may fail',
                details={'tv_type': tv_type},
                source='schedule'
            )
        if tv_type == 'samsung':
            # For Samsung: use close_menu=True to exit Smart Hub after boot
            # This matches the behavior expected by users
            tv.power_on(close_menu=True, wait_time=wait_time)
        else:
            tv.power_on()
        set_cached_power_state('on')

        # 2. Warten bis TV bereit ist (only for non-Samsung, since Samsung waits in power_on)
        if tv_type != 'samsung':
            print(f"[Startup] Warte {wait_time}s bis TV bereit ist...", flush=True)
            time.sleep(wait_time)
    else:
        print(f"[Startup] TV already on - skipping power-on and wait", flush=True)

    # 3. For Philips: Switch to TV mode first (starts in Home screen)
    if tv_type == 'philips' and channel is not None and not tv_already_on:
        print(f"[Startup] Philips: Wechsle zu TV-Modus...", flush=True)
        try:
            if hasattr(tv, 'switch_to_tv'):
                tv.switch_to_tv()
                time.sleep(2)  # Wait for TV mode to activate
        except Exception as e:
            log_event(
                level='WARNING',
                category='schedule',
                message=f'TV-Modus konnte nicht aktiviert werden: {e}',
                details={'error': str(e)},
                source='schedule'
            )

    # 4. Optional: Lautstärke setzen
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

    # 5. Optional: Kanal wechseln
    if channel is not None:
        print(f"[Startup] Wechsle zu Kanal {channel}...", flush=True)
        try:
            # For Philips, use set_channel method if available
            if tv_type == 'philips' and hasattr(tv, 'set_channel'):
                tv.set_channel(channel)
            else:
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
    from ..models import Scenario, db

    scenario_id = action_data.get('scenario_id')
    if scenario_id:
        scenario = db.session.get(Scenario, scenario_id)
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
