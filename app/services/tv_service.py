"""
TV-Service - Wrapper um samsung_tv.py mit Konfigurationsverwaltung
"""
import os
import sys
from typing import Optional
from flask import current_app

# Pfad zum samsung_tv.py Modul hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from samsung_tv import SamsungTV, Key, TVInfo

# Globale TV-Instanz
_tv_instance: Optional[SamsungTV] = None


def get_tv_service() -> SamsungTV:
    """TV-Service-Instanz abrufen oder erstellen"""
    global _tv_instance

    if _tv_instance is None:
        _tv_instance = _create_tv_instance()

    return _tv_instance


def reinit_tv_service():
    """TV-Service neu initialisieren (nach Konfigurationsänderung)"""
    global _tv_instance
    _tv_instance = _create_tv_instance()


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
__all__ = ['get_tv_service', 'reinit_tv_service', 'SamsungTV', 'Key', 'TVInfo', 'TVServiceWrapper']
