"""
Backup-Service für Konfiguration und Daten
"""
import os
import json
import shutil
import subprocess
from datetime import datetime
from typing import Optional
from flask import current_app


def create_backup(destination: str = None) -> str:
    """
    Backup der Datenbank und Konfiguration erstellen.

    Args:
        destination: Zielverzeichnis (Standard: instance/backups)

    Returns:
        Pfad zur erstellten Backup-Datei
    """
    from ..models import db, Config, Schedule, Scenario, Log

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'tvremote_backup_{timestamp}'

    # Temporäres Backup-Verzeichnis
    instance_dir = os.path.join(os.path.dirname(current_app.root_path), 'instance')
    backup_dir = os.path.join(instance_dir, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    temp_dir = os.path.join(backup_dir, backup_name)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Datenbank kopieren
        db_path = os.path.join(instance_dir, 'tvremote.db')
        if os.path.exists(db_path):
            shutil.copy2(db_path, os.path.join(temp_dir, 'tvremote.db'))

        # Token-Datei kopieren
        token_path = current_app.config['TV_TOKEN_FILE']
        if os.path.exists(token_path):
            shutil.copy2(token_path, os.path.join(temp_dir, 'tv_token'))

        # Konfiguration als JSON exportieren
        config_data = {
            'exported_at': datetime.now().isoformat(),
            'config': {},
            'schedules': [],
            'scenarios': []
        }

        # Konfigurationswerte
        for config in Config.query.all():
            config_data['config'][config.key] = config.value

        # Zeitpläne (ohne Logs)
        for schedule in Schedule.query.all():
            config_data['schedules'].append({
                'name': schedule.name,
                'description': schedule.description,
                'cron_expression': schedule.cron_expression,
                'action_type': schedule.action_type,
                'action_data': schedule.get_action_data(),
                'enabled': schedule.enabled
            })

        # Szenarien
        for scenario in Scenario.query.all():
            if not scenario.is_builtin:  # Nur benutzerdefinierte
                config_data['scenarios'].append({
                    'name': scenario.name,
                    'description': scenario.description,
                    'steps': scenario.get_steps(),
                    'randomize_delays': scenario.randomize_delays,
                    'min_delay_ms': scenario.min_delay_ms,
                    'max_delay_ms': scenario.max_delay_ms
                })

        with open(os.path.join(temp_dir, 'config.json'), 'w') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        # ZIP-Archiv erstellen
        archive_path = shutil.make_archive(
            os.path.join(backup_dir, backup_name),
            'zip',
            temp_dir
        )

        # Temporäres Verzeichnis löschen
        shutil.rmtree(temp_dir)

        # Auf NAS kopieren wenn konfiguriert
        backup_method = current_app.config.get('BACKUP_METHOD', 'local')
        if backup_method == 'ssh':
            _upload_to_nas(archive_path)

        return archive_path

    except Exception as e:
        # Aufräumen bei Fehler
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e


def _upload_to_nas(local_path: str):
    """Backup via SSH auf NAS hochladen"""
    ssh_host = current_app.config.get('BACKUP_SSH_HOST')
    ssh_user = current_app.config.get('BACKUP_SSH_USER')
    ssh_path = current_app.config.get('BACKUP_SSH_PATH')

    if not all([ssh_host, ssh_user, ssh_path]):
        raise ValueError('SSH-Backup-Konfiguration unvollständig')

    # scp verwenden
    remote_path = f'{ssh_user}@{ssh_host}:{ssh_path}/'
    filename = os.path.basename(local_path)

    result = subprocess.run(
        ['scp', '-o', 'StrictHostKeyChecking=no', local_path, remote_path],
        capture_output=True,
        text=True,
        timeout=300
    )

    if result.returncode != 0:
        raise Exception(f'SCP fehlgeschlagen: {result.stderr}')

    from .logger import log_event
    log_event(
        level='INFO',
        category='system',
        message='Backup auf NAS hochgeladen',
        details={'host': ssh_host, 'path': ssh_path, 'file': filename},
        source='system'
    )


def restore_backup(backup_path: str):
    """
    Backup wiederherstellen.

    Args:
        backup_path: Pfad zur ZIP-Backup-Datei
    """
    import zipfile
    from ..models import db, Config, Schedule, Scenario

    instance_dir = os.path.join(os.path.dirname(current_app.root_path), 'instance')
    temp_dir = os.path.join(instance_dir, 'restore_temp')

    try:
        # ZIP entpacken
        with zipfile.ZipFile(backup_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)

        # Datenbank wiederherstellen
        db_backup = os.path.join(temp_dir, 'tvremote.db')
        if os.path.exists(db_backup):
            db_path = os.path.join(instance_dir, 'tvremote.db')
            shutil.copy2(db_backup, db_path)

        # Token wiederherstellen
        token_backup = os.path.join(temp_dir, 'tv_token')
        if os.path.exists(token_backup):
            token_path = current_app.config['TV_TOKEN_FILE']
            shutil.copy2(token_backup, token_path)

        # Aufräumen
        shutil.rmtree(temp_dir)

        from .logger import log_event
        log_event(
            level='INFO',
            category='system',
            message='Backup wiederhergestellt',
            details={'backup_file': os.path.basename(backup_path)},
            source='system'
        )

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e


def list_backups() -> list:
    """Verfügbare lokale Backups auflisten"""
    instance_dir = os.path.join(os.path.dirname(current_app.root_path), 'instance')
    backup_dir = os.path.join(instance_dir, 'backups')

    if not os.path.exists(backup_dir):
        return []

    backups = []
    for filename in os.listdir(backup_dir):
        if filename.endswith('.zip') and filename.startswith('tvremote_backup_'):
            filepath = os.path.join(backup_dir, filename)
            stat = os.stat(filepath)
            backups.append({
                'filename': filename,
                'path': filepath,
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

    return sorted(backups, key=lambda x: x['created'], reverse=True)
