"""
TV-Service - Wrapper um samsung_tv.py mit Konfigurationsverwaltung
"""
import os
import sys
import time
from typing import Optional, Tuple
from flask import current_app

# Pfad zum samsung_tv.py Modul hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from samsung_tv import SamsungTV, Key, TVInfo

# Globale TV-Instanz
_tv_instance: Optional[SamsungTV] = None

# Cache for TV status to avoid repeated checks
_status_cache: dict = {
    'connected': None,
    'power_state': None,
    'info': None,
    'last_check': 0
}
CACHE_TTL_SECONDS = 10  # Cache TV status for 10 seconds (shorter for responsiveness)


class MockSamsungTV:
    """Mock TV for testing"""
    is_paired = False

    def __init__(self):
        self.ip = '192.168.1.1'
        self.mac = '00:00:00:00:00:00'
        self._volume = 20
        self._muted = False

    def get_info(self):
        return None

    def is_connected(self):
        return False

    def is_on(self):
        return False

    def ping(self, timeout=2.0):
        return False

    def send_key(self, key, delay=0.3):
        return True

    def send_keys(self, keys, delay=0.3):
        return True

    def hold_key(self, key, seconds=1.0):
        return True

    def send_text(self, text):
        return True

    def move_cursor(self, x, y, duration=0):
        return True

    def power_on(self, close_menu=False, wait_time=5.0):
        return True

    def power_off(self):
        return True

    def close_menu(self):
        return True

    def mute(self):
        self._muted = not self._muted
        return True

    def volume_up(self, steps=1):
        self._volume = min(100, self._volume + steps)
        return True

    def volume_down(self, steps=1):
        self._volume = max(0, self._volume - steps)
        return True

    def get_volume(self):
        return self._volume

    def set_volume(self, volume):
        self._volume = max(0, min(100, volume))
        return True

    def get_mute_status(self):
        return self._muted

    def set_mute(self, muted):
        self._muted = muted
        return True

    def channel_up(self):
        return True

    def channel_down(self):
        return True

    def channel(self, num):
        return True

    def run_app(self, app_id):
        return True

    def close_app(self, app_id):
        return True

    def get_app_status(self, app_id):
        return None

    def home(self):
        return True

    def back(self):
        return True

    def exit(self):
        return True


def get_tv_service() -> SamsungTV:
    """TV-Service-Instanz abrufen oder erstellen"""
    global _tv_instance

    # Return mock for testing
    try:
        if current_app.config.get('TESTING'):
            return MockSamsungTV()
    except RuntimeError:
        pass

    if _tv_instance is None:
        _tv_instance = _create_tv_instance()

    return _tv_instance


def reinit_tv_service():
    """TV-Service neu initialisieren (nach Konfigurationsänderung)"""
    global _tv_instance
    _tv_instance = _create_tv_instance()
    invalidate_status_cache()


def invalidate_status_cache():
    """Invalidate the status cache to force a fresh check"""
    global _status_cache
    _status_cache['last_check'] = 0


def set_cached_power_state(power_state: str):
    """
    Set the expected power state in cache and database after a power action.
    Using database ensures state is shared across Flask processes.
    """
    global _status_cache
    _status_cache['power_state'] = power_state
    if power_state == 'on':
        # TV is turning on - mark as connected (optimistic)
        _status_cache['connected'] = True
    elif power_state in ('off', 'standby'):
        # TV is off - mark as not connected since it won't respond
        _status_cache['connected'] = False
        _status_cache['info'] = None
    _status_cache['last_check'] = time.time()

    # Also update database for cross-process sharing
    try:
        from flask import current_app
        if current_app:
            from ..models import TVState, db
            from datetime import datetime
            tv_state = TVState.get_instance()
            tv_state.power_state = power_state
            tv_state.last_updated = datetime.utcnow()
            db.session.commit()
    except (RuntimeError, Exception):
        pass  # Outside app context or DB error - memory cache still updated


def get_cached_status(force_refresh: bool = False) -> dict:
    """
    Get TV status with caching to avoid repeated network calls.
    Returns cached status if still valid, otherwise fetches fresh status.
    Uses database for cross-process state sharing.
    """
    global _status_cache

    now = time.time()
    cache_age = now - _status_cache['last_check']

    # Check database for recent state updates from other processes
    db_power_state = None
    db_updated = None
    try:
        from flask import current_app
        if current_app:
            from ..models import TVState
            tv_state = TVState.get_instance()
            db_power_state = tv_state.power_state
            db_updated = tv_state.last_updated
    except (RuntimeError, Exception):
        pass

    # If database was updated more recently than our cache, use DB state
    if db_updated and db_power_state:
        db_age = (now - db_updated.timestamp()) if db_updated else float('inf')
        if db_age < cache_age and db_age < CACHE_TTL_SECONDS:
            connected = db_power_state == 'on'
            return {
                'connected': connected,
                'power_state': db_power_state,
                'info': _status_cache.get('info'),
                'cached': True,
                'cache_age': db_age
            }

    # Return memory cached status if still valid
    if not force_refresh and cache_age < CACHE_TTL_SECONDS and _status_cache['connected'] is not None:
        return {
            'connected': _status_cache['connected'],
            'power_state': _status_cache['power_state'],
            'info': _status_cache['info'],
            'cached': True,
            'cache_age': cache_age
        }

    # Fetch fresh status from TV
    tv = get_tv_service()
    connected = False
    power_state = 'unknown'
    info = None

    try:
        info = tv.get_info()
        if info:
            connected = True
            power_state = info.power_state
    except Exception:
        # TV not responding - check if we have a recent DB state
        if db_power_state and db_power_state in ('off', 'standby'):
            power_state = db_power_state

    # Update memory cache
    _status_cache['connected'] = connected
    _status_cache['power_state'] = power_state
    _status_cache['info'] = info
    _status_cache['last_check'] = now

    return {
        'connected': connected,
        'power_state': power_state,
        'info': info,
        'cached': False,
        'cache_age': 0
    }


def _create_tv_instance() -> SamsungTV:
    """Neue TV-Instanz erstellen mit Konfiguration aus DB oder Config"""
    from ..models import Config as ConfigModel

    # Werte aus Datenbank oder Fallback auf App-Config
    try:
        tv_ip = ConfigModel.get('tv_ip') or current_app.config['TV_IP']
        tv_mac = ConfigModel.get('tv_mac') or current_app.config['TV_MAC']
        tv_token_file = current_app.config['TV_TOKEN_FILE']
    except RuntimeError:
        # Außerhalb des App-Kontexts (z.B. bei CLI-Nutzung)
        tv_ip = os.environ.get('TV_IP', '192.168.178.103')
        tv_mac = os.environ.get('TV_MAC', '80:47:86:E9:B2:17')
        tv_token_file = os.path.expanduser('~/.tv_token')

    return SamsungTV(
        ip=tv_ip,
        mac=tv_mac,
        token_file=tv_token_file,
        app_name='TVFernbedienung'
    )


class TVServiceWrapper:
    """
    Erweiterter Wrapper um SamsungTV mit zusätzlichen Funktionen
    für die Webanwendung.
    """

    def __init__(self, tv: SamsungTV):
        self.tv = tv

    def is_connected(self) -> bool:
        """Prüfen ob TV erreichbar ist"""
        try:
            info = self.tv.get_info()
            return info is not None
        except Exception:
            return False

    def get_status(self) -> dict:
        """Erweiterten Status abrufen"""
        from ..models import TVState

        tv_state = TVState.get_instance()
        info = None

        try:
            info = self.tv.get_info()
            if info:
                tv_state.power_state = info.power_state
        except Exception:
            pass

        return {
            'connected': info is not None,
            'power_state': tv_state.power_state,
            'estimated_volume': tv_state.estimated_volume,
            'estimated_channel': tv_state.estimated_channel,
            'estimated_muted': tv_state.estimated_muted,
            'info': info
        }

    def update_estimated_state(self, action: str, value=None):
        """
        Geschätzten Zustand nach einer Aktion aktualisieren
        """
        from ..models import TVState, db
        from datetime import datetime

        tv_state = TVState.get_instance()
        tv_state.last_updated = datetime.utcnow()

        if action == 'volume_up':
            if tv_state.estimated_volume is not None:
                tv_state.estimated_volume = min(100, tv_state.estimated_volume + (value or 1))
        elif action == 'volume_down':
            if tv_state.estimated_volume is not None:
                tv_state.estimated_volume = max(0, tv_state.estimated_volume - (value or 1))
        elif action == 'mute':
            tv_state.estimated_muted = not tv_state.estimated_muted
        elif action == 'channel':
            tv_state.estimated_channel = value
        elif action == 'channel_up':
            if tv_state.estimated_channel is not None:
                tv_state.estimated_channel += 1
        elif action == 'channel_down':
            if tv_state.estimated_channel is not None:
                tv_state.estimated_channel = max(1, tv_state.estimated_channel - 1)
        elif action == 'power_on':
            tv_state.power_state = 'on'
        elif action == 'power_off':
            tv_state.power_state = 'standby'

        db.session.commit()


# Export der Key-Enum für einfachen Import
__all__ = ['get_tv_service', 'reinit_tv_service', 'get_cached_status', 'invalidate_status_cache', 'set_cached_power_state', 'SamsungTV', 'Key', 'TVInfo', 'TVServiceWrapper']
