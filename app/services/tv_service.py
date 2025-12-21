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
    'last_check': 0,
    'transition_until': 0,  # Timestamp when transition state ends
    'transition_started': 0,  # Timestamp when transition began
    'transition_type': None,  # 'turning_on' or 'turning_off'
    'target_state': None,  # Expected state after transition ('on' or 'off')
    'just_confirmed': False,  # True when transition just completed
    'confirmed_at': 0,  # Timestamp when state was confirmed
    'unreachable_since': 0  # Timestamp when TV first became unreachable during shutdown
}
CACHE_TTL_SECONDS = 10  # Cache TV status for 10 seconds (shorter for responsiveness)

# Maximum transition duration (safety timeout if API never confirms)
MAX_TRANSITION_SECONDS = 60  # Give up after 60 seconds if API never confirms

# Minimum time to show transition state before checking API
# Keep this short to not miss standby phase, but long enough to avoid immediate flicker
MIN_TRANSITION_SECONDS = 0.5

# Minimum time unreachable during shutdown before marking as fully off
# Wait a bit to ensure TV is truly off, not just temporarily unreachable
MIN_SHUTTING_DOWN_SECONDS = 3


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


def set_cached_power_state(power_state: str, is_transition: bool = True):
    """
    Set the expected power state in cache and database after a power action.
    Using database ensures state is shared across Flask processes.

    Args:
        power_state: 'on', 'off', 'standby', 'turning_on', 'turning_off'
        is_transition: If True, sets a transition timer during which state is locked
    """
    global _status_cache
    now = time.time()

    if power_state == 'on' or power_state == 'turning_on':
        # TV is turning on - set transition state
        _status_cache['power_state'] = 'turning_on' if is_transition else 'on'
        _status_cache['connected'] = False  # Not connected yet
        _status_cache['info'] = None
        _status_cache['target_state'] = 'on'  # Remember expected end state
        if is_transition:
            _status_cache['transition_until'] = now + MAX_TRANSITION_SECONDS
            _status_cache['transition_started'] = now
            _status_cache['transition_type'] = 'turning_on'
    elif power_state in ('off', 'standby', 'turning_off'):
        # TV is turning off - set transition state
        _status_cache['power_state'] = 'turning_off' if is_transition else 'off'
        _status_cache['connected'] = False
        _status_cache['info'] = None
        _status_cache['target_state'] = 'off'  # Remember expected end state
        if is_transition:
            _status_cache['transition_until'] = now + MAX_TRANSITION_SECONDS
            _status_cache['transition_started'] = now
            _status_cache['transition_type'] = 'turning_off'

    _status_cache['last_check'] = now

    # Also update database for cross-process sharing
    try:
        from flask import current_app
        if current_app:
            from ..models import TVState, db
            from datetime import datetime
            tv_state = TVState.get_instance()
            # Store the actual target state, not transition state
            tv_state.power_state = 'on' if power_state in ('on', 'turning_on') else 'off'
            tv_state.last_updated = datetime.utcnow()
            db.session.commit()
    except (RuntimeError, Exception):
        pass  # Outside app context or DB error - memory cache still updated


def get_cached_status(force_refresh: bool = False) -> dict:
    """
    Get TV status with caching to avoid repeated network calls.
    Returns cached status if still valid, otherwise fetches fresh status.
    Uses database for cross-process state sharing.

    Returns dict with:
        - connected: bool - TV is responding to API
        - power_state: str - 'on', 'off', 'turning_on', 'turning_off'
        - info: TVInfo or None
        - in_transition: bool - TV is in power transition
        - transition_type: str or None - 'turning_on' or 'turning_off'
    """
    global _status_cache

    now = time.time()
    cache_age = now - _status_cache['last_check']

    # Check if we're in a transition state (power button was just pressed)
    in_transition = now < _status_cache.get('transition_until', 0)
    transition_type = _status_cache.get('transition_type') if in_transition else None
    target_state = _status_cache.get('target_state')  # 'on' or 'off' - the ultimate goal

    # During transition, actively check if TV has reached target state
    if in_transition:
        transition_started = _status_cache.get('transition_started', 0)
        transition_age = now - transition_started

        # Safety check: if transition_type is None but we're still in transition,
        # derive it from target_state to prevent showing wrong state
        if transition_type is None and target_state:
            transition_type = 'turning_on' if target_state == 'on' else 'turning_off'

        # If we still don't know the transition type, clear transition and return cached state
        if transition_type is None:
            _status_cache['transition_until'] = 0
            # Fall through to normal cache logic below

        else:
            # During the first few seconds, don't check API - just show transition state
            # This prevents flickering on slow connections where command hasn't taken effect
            if transition_age < MIN_TRANSITION_SECONDS:
                return {
                    'connected': False,
                    'power_state': transition_type,
                    'info': None,
                    'cached': True,
                    'cache_age': 0,
                    'in_transition': True,
                    'transition_type': transition_type,
                    'transition_remaining': int(_status_cache['transition_until'] - now)
                }

            tv = get_tv_service()
            try:
                # Quick ping first to avoid long blocking timeouts during shutdown
                # ping() uses 1-second timeout vs get_info()'s 5-10 seconds
                if not tv.ping(timeout=1.0):
                    # TV not reachable - determine outcome based on target_state
                    if target_state == 'off' or transition_type in ('turning_off', 'shutting_down'):
                        # Target was off and TV is unreachable
                        # Track how long it's been unreachable before declaring it off
                        unreachable_since = _status_cache.get('unreachable_since', 0)
                        if unreachable_since == 0:
                            # First time we noticed it's unreachable - start tracking
                            print(f"[TV Service] TV became unreachable during shutdown - waiting {MIN_SHUTTING_DOWN_SECONDS}s before marking off", flush=True)
                            _status_cache['unreachable_since'] = now
                            unreachable_since = now

                        unreachable_duration = now - unreachable_since

                        if unreachable_duration >= MIN_SHUTTING_DOWN_SECONDS:
                            # Been unreachable long enough - now it's truly off
                            if _status_cache.get('transition_type') in ('turning_off', 'shutting_down'):
                                print(f"[TV Service] TV is now OFF (unreachable for {unreachable_duration:.1f}s) - fully powered down", flush=True)
                            _status_cache['transition_until'] = 0
                            _status_cache['transition_type'] = None
                            _status_cache['target_state'] = None
                            _status_cache['connected'] = False
                            _status_cache['power_state'] = 'off'
                            _status_cache['info'] = None
                            _status_cache['last_check'] = now
                            _status_cache['just_confirmed'] = True
                            _status_cache['confirmed_at'] = now
                            _status_cache['unreachable_since'] = 0  # Reset tracker
                            return {
                                'connected': False,
                                'power_state': 'off',
                                'info': None,
                                'cached': False,
                                'cache_age': 0,
                                'in_transition': False,
                                'transition_type': None,
                                'just_confirmed': True
                            }
                        else:
                            # Still in the waiting period - show standby
                            remaining_wait = MIN_SHUTTING_DOWN_SECONDS - unreachable_duration
                            return {
                                'connected': False,
                                'power_state': 'standby',
                                'info': None,
                                'cached': False,
                                'cache_age': 0,
                                'in_transition': True,
                                'transition_type': 'shutting_down',
                                'transition_remaining': int(remaining_wait)
                            }
                    elif target_state == 'on' or transition_type == 'turning_on':
                        # Target was on but TV not reachable - still booting
                        return {
                            'connected': False,
                            'power_state': 'turning_on',
                            'info': None,
                            'cached': True,
                            'cache_age': cache_age,
                            'in_transition': True,
                            'transition_type': 'turning_on',
                            'transition_remaining': int(_status_cache['transition_until'] - now)
                        }
                    else:
                        # Unknown state - shouldn't happen, but default to off for safety
                        _status_cache['transition_until'] = 0
                        _status_cache['transition_type'] = None
                        return {
                            'connected': False,
                            'power_state': 'off',
                            'info': None,
                            'cached': True,
                            'cache_age': 0,
                            'in_transition': False,
                            'transition_type': None
                        }

                # Ping succeeded - TV is reachable again
                # Reset unreachable tracker since TV is responding
                if _status_cache.get('unreachable_since', 0) > 0:
                    print(f"[TV Service] TV is reachable again - clearing unreachable tracker", flush=True)
                    _status_cache['unreachable_since'] = 0

                # Now safe to call get_info() (TV is responsive)
                info = tv.get_info()
                if transition_type == 'turning_on' and info and info.power_state == 'on':
                    # TV is now on - clear transition and mark as just confirmed
                    # Check if we haven't already confirmed this transition (avoid duplicate logs)
                    if _status_cache.get('transition_type') == 'turning_on':
                        print(f"[TV Service] TV is now ON - transition complete", flush=True)
                        _status_cache['transition_until'] = 0
                        _status_cache['transition_type'] = None
                        _status_cache['target_state'] = None
                        _status_cache['connected'] = True
                        _status_cache['power_state'] = 'on'
                        _status_cache['info'] = info
                        _status_cache['last_check'] = now
                        _status_cache['just_confirmed'] = True
                        _status_cache['confirmed_at'] = now
                    return {
                        'connected': True,
                        'power_state': 'on',
                        'info': info,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': False,
                        'transition_type': None,
                        'just_confirmed': _status_cache.get('just_confirmed', False)
                    }
                elif transition_type == 'turning_on' and info and info.power_state != 'on':
                    # TV is responding but not fully on yet (still booting)
                    # Keep showing transition state
                    return {
                        'connected': True,
                        'power_state': 'turning_on',
                        'info': info,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': True,
                        'transition_type': 'turning_on',
                        'transition_remaining': int(_status_cache['transition_until'] - now)
                    }
                elif transition_type == 'turning_on' and info is None:
                    # TV not responding yet during turn-on - still booting
                    # Keep showing transition state
                    return {
                        'connected': False,
                        'power_state': 'turning_on',
                        'info': None,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': True,
                        'transition_type': 'turning_on',
                        'transition_remaining': int(_status_cache['transition_until'] - now)
                    }
                elif transition_type == 'turning_off' and info and info.power_state == 'on':
                    # TV still reports as on - power-off command hasn't taken effect yet
                    # Keep showing transition state to prevent flickering
                    return {
                        'connected': True,
                        'power_state': 'turning_off',
                        'info': info,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': True,
                        'transition_type': 'turning_off',
                        'transition_remaining': int(_status_cache['transition_until'] - now)
                    }
                elif transition_type == 'turning_off' and info and info.power_state != 'on':
                    # TV is in standby - screen off but hardware still running
                    # But first check if another request already detected off
                    if _status_cache.get('power_state') == 'off':
                        return {
                            'connected': False,
                            'power_state': 'off',
                            'info': None,
                            'cached': True,
                            'cache_age': 0,
                            'in_transition': False,
                            'transition_type': None,
                            'just_confirmed': _status_cache.get('just_confirmed', False)
                        }
                    # Only log once when first entering standby state
                    if _status_cache.get('transition_type') == 'turning_off':
                        print(f"[TV Service] TV is in STANDBY - hardware shutting down", flush=True)
                        _status_cache['transition_type'] = 'shutting_down'  # Update to avoid re-logging
                        _status_cache['power_state'] = 'standby'
                        _status_cache['connected'] = True
                        _status_cache['info'] = info
                        _status_cache['last_check'] = now
                    # Return standby state - keep polling to detect when fully off
                    return {
                        'connected': True,
                        'power_state': 'standby',
                        'info': info,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': True,  # Keep polling
                        'transition_type': 'shutting_down',  # Different type for UI
                        'transition_remaining': int(_status_cache['transition_until'] - now)
                    }
                elif transition_type == 'shutting_down' and info and info.power_state != 'on':
                    # Still in standby - but check if another request already detected off
                    if _status_cache.get('power_state') == 'off':
                        return {
                            'connected': False,
                            'power_state': 'off',
                            'info': None,
                            'cached': True,
                            'cache_age': 0,
                            'in_transition': False,
                            'transition_type': None,
                            'just_confirmed': _status_cache.get('just_confirmed', False)
                        }
                    # Still in standby - keep polling silently
                    return {
                        'connected': True,
                        'power_state': 'standby',
                        'info': info,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': True,
                        'transition_type': 'shutting_down',
                        'transition_remaining': int(_status_cache['transition_until'] - now)
                    }
                elif info is None and (target_state == 'off' or transition_type in ('turning_off', 'shutting_down')):
                    # TV is now fully off (unreachable) and we were turning off
                    if _status_cache.get('transition_type') in ('turning_off', 'shutting_down'):
                        print(f"[TV Service] TV is now OFF (unreachable) - fully powered down", flush=True)
                    _status_cache['transition_until'] = 0
                    _status_cache['transition_type'] = None
                    _status_cache['target_state'] = None
                    _status_cache['connected'] = False
                    _status_cache['power_state'] = 'off'
                    _status_cache['info'] = None
                    _status_cache['last_check'] = now
                    _status_cache['just_confirmed'] = True
                    _status_cache['confirmed_at'] = now
                    return {
                        'connected': False,
                        'power_state': 'off',
                        'info': None,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': False,
                        'transition_type': None,
                        'just_confirmed': True
                    }
                elif info is None and (target_state == 'on' or transition_type == 'turning_on'):
                    # TV not responding during turn-on - still booting
                    return {
                        'connected': False,
                        'power_state': 'turning_on',
                        'info': None,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': True,
                        'transition_type': 'turning_on',
                        'transition_remaining': int(_status_cache['transition_until'] - now)
                    }
            except Exception as e:
                # API call failed - determine outcome based on target_state
                if target_state == 'off' or transition_type in ('turning_off', 'shutting_down'):
                    # Target was off and API failed - TV is fully off
                    if _status_cache.get('transition_type') in ('turning_off', 'shutting_down'):
                        print(f"[TV Service] TV unreachable - fully powered down", flush=True)
                    _status_cache['transition_until'] = 0
                    _status_cache['transition_type'] = None
                    _status_cache['target_state'] = None
                    _status_cache['connected'] = False
                    _status_cache['power_state'] = 'off'
                    _status_cache['info'] = None
                    _status_cache['last_check'] = now
                    _status_cache['just_confirmed'] = True
                    _status_cache['confirmed_at'] = now
                    return {
                        'connected': False,
                        'power_state': 'off',
                        'info': None,
                        'cached': False,
                        'cache_age': 0,
                        'in_transition': False,
                        'transition_type': None,
                        'just_confirmed': True
                    }
                # Target was on but API failed - still booting, keep transition
                # (fall through to transition state below)

            # Still in transition - but check if another request already detected completion
            if _status_cache.get('power_state') == 'off' and _status_cache.get('transition_type') is None:
                return {
                    'connected': False,
                    'power_state': 'off',
                    'info': None,
                    'cached': True,
                    'cache_age': 0,
                    'in_transition': False,
                    'transition_type': None,
                    'just_confirmed': _status_cache.get('just_confirmed', False)
                }
            if _status_cache.get('power_state') == 'on' and _status_cache.get('transition_type') is None:
                return {
                    'connected': True,
                    'power_state': 'on',
                    'info': _status_cache.get('info'),
                    'cached': True,
                    'cache_age': 0,
                    'in_transition': False,
                    'transition_type': None,
                    'just_confirmed': _status_cache.get('just_confirmed', False)
                }

            # Still in transition - return transition state based on target_state for safety
            current_transition = _status_cache.get('transition_type') or transition_type
            if current_transition is None:
                # Derive from target_state if we still don't know
                current_transition = 'turning_on' if target_state == 'on' else 'turning_off' if target_state == 'off' else 'turning_off'
            return {
                'connected': False,
                'power_state': current_transition,
                'info': None,
                'cached': True,
                'cache_age': cache_age,
                'in_transition': True,
                'transition_type': current_transition,
                'transition_remaining': int(_status_cache['transition_until'] - now)
            }

    # Safety timeout expired - assume target state was reached if we have one
    target_state = _status_cache.get('target_state')
    expired_transition_type = _status_cache.get('transition_type')
    if target_state and expired_transition_type:
        print(f"[TV Service] Transition timeout - assuming target state: {target_state}", flush=True)
        _status_cache['transition_until'] = 0
        _status_cache['transition_type'] = None
        _status_cache['power_state'] = target_state
        _status_cache['connected'] = (target_state == 'on')
        _status_cache['target_state'] = None
        _status_cache['last_check'] = now
        _status_cache['just_confirmed'] = True
        _status_cache['confirmed_at'] = now
        return {
            'connected': (target_state == 'on'),
            'power_state': target_state,
            'info': None,
            'cached': False,
            'cache_age': 0,
            'in_transition': False,
            'transition_type': None,
            'just_confirmed': True
        }

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

    # Check if we recently confirmed state (show for 3 seconds)
    just_confirmed = False
    confirmed_age = now - _status_cache.get('confirmed_at', 0)
    if _status_cache.get('just_confirmed') and confirmed_age < 3:
        just_confirmed = True
    elif _status_cache.get('just_confirmed'):
        # Clear the flag after 3 seconds
        _status_cache['just_confirmed'] = False

    # Return memory cached status if still valid
    if not force_refresh and cache_age < CACHE_TTL_SECONDS and _status_cache['connected'] is not None:
        power_state = _status_cache['power_state']
        # Normalize standby to off for UI consistency
        if power_state == 'standby':
            power_state = 'off'
        return {
            'connected': _status_cache['connected'],
            'power_state': power_state,
            'info': _status_cache['info'],
            'cached': True,
            'cache_age': cache_age,
            'in_transition': False,
            'transition_type': None,
            'just_confirmed': just_confirmed
        }

    # Fetch fresh status from TV
    tv = get_tv_service()
    connected = False
    power_state = 'off'  # Default to off if not reachable
    info = None

    try:
        # Quick ping check first to avoid long blocking timeouts
        if not tv.ping(timeout=1.0):
            # TV not responding to ping
            # If we recently confirmed TV was on, trust that state longer
            confirmed_age = now - _status_cache.get('confirmed_at', 0)
            last_power_state = _status_cache.get('power_state')
            if last_power_state == 'on' and confirmed_age < 30:
                # Recently confirmed on - likely just a slow network, keep showing on
                return {
                    'connected': False,
                    'power_state': 'on',
                    'info': _status_cache.get('info'),
                    'cached': True,
                    'cache_age': cache_age,
                    'in_transition': False,
                    'transition_type': None,
                    'just_confirmed': just_confirmed
                }
            # Otherwise assume off
            power_state = 'off'
        else:
            # Ping succeeded - try to get full info
            info = tv.get_info()
            if info:
                connected = True
                # Map TV's power_state to our simplified model
                if info.power_state == 'on':
                    power_state = 'on'
                else:
                    # 'standby' or any other state = off for our purposes
                    power_state = 'off'
    except Exception:
        # TV not responding - check if we recently confirmed it was on
        confirmed_age = now - _status_cache.get('confirmed_at', 0)
        last_power_state = _status_cache.get('power_state')
        if last_power_state == 'on' and confirmed_age < 30:
            # Recently confirmed on - likely just a temporary network issue
            return {
                'connected': False,
                'power_state': 'on',
                'info': _status_cache.get('info'),
                'cached': True,
                'cache_age': cache_age,
                'in_transition': False,
                'transition_type': None,
                'just_confirmed': just_confirmed
            }
        power_state = 'off'

    # Update memory cache
    _status_cache['connected'] = connected
    _status_cache['power_state'] = power_state
    _status_cache['info'] = info
    _status_cache['last_check'] = now
    # Clear target state once we have a confirmed state
    if connected:
        _status_cache['target_state'] = None

    return {
        'connected': connected,
        'power_state': power_state,
        'info': info,
        'cached': False,
        'cache_age': 0,
        'in_transition': False,
        'transition_type': None,
        'just_confirmed': just_confirmed
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

    print(f"[TV Service] Creating TV instance: ip={tv_ip}, token_file={tv_token_file}", flush=True)

    tv = SamsungTV(
        ip=tv_ip,
        mac=tv_mac,
        token_file=tv_token_file,
        app_name='TVFernbedienung'
    )

    # Fallback: If token file is empty/missing, try to restore from database
    if not tv.is_paired:
        try:
            db_token = ConfigModel.get('tv_token')
            if db_token:
                print(f"[TV Service] Restoring token from database to file", flush=True)
                # Write token to file for future use
                try:
                    token_dir = os.path.dirname(tv_token_file)
                    if token_dir and not os.path.exists(token_dir):
                        os.makedirs(token_dir, exist_ok=True)
                    with open(tv_token_file, 'w') as f:
                        f.write(db_token)
                    # Reload token into TV instance
                    tv._token = db_token
                    print(f"[TV Service] Token restored from database successfully", flush=True)
                except PermissionError as e:
                    print(f"[TV Service] Cannot write token file (permission denied): {e}", flush=True)
                    # Still use the token in memory even if we can't write file
                    tv._token = db_token
                except Exception as e:
                    print(f"[TV Service] Error writing token file: {e}", flush=True)
                    tv._token = db_token
        except Exception as e:
            print(f"[TV Service] Could not restore token from database: {e}", flush=True)

    return tv


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
