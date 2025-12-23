"""
Base TV Service Interface - Abstract base class for TV implementations
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class TVInfo:
    """Common TV information structure"""
    name: str
    model: str
    model_name: Optional[str] = None
    ip: Optional[str] = None
    mac: Optional[str] = None
    power_state: str = 'unknown'
    firmware: Optional[str] = None
    os: Optional[str] = None
    resolution: Optional[str] = None
    uuid: Optional[str] = None


class BaseTVService(ABC):
    """Abstract base class for TV service implementations"""

    def __init__(self, ip: str, mac: Optional[str] = None):
        self.ip = ip
        self.mac = mac

    @property
    @abstractmethod
    def tv_type(self) -> str:
        """Return TV type identifier ('samsung' or 'philips')"""
        pass

    @property
    @abstractmethod
    def is_paired(self) -> bool:
        """Check if TV is paired/authenticated"""
        pass

    @abstractmethod
    def pair(self, **kwargs) -> bool:
        """
        Initiate pairing with TV.

        For Samsung: Shows prompt on TV screen
        For Philips: Requires PIN callback

        Returns True if pairing successful
        """
        pass

    @abstractmethod
    def ping(self, timeout: float = 2.0) -> bool:
        """Quick check if TV is reachable"""
        pass

    @abstractmethod
    def get_info(self) -> Optional[TVInfo]:
        """Get TV information"""
        pass

    @abstractmethod
    def power_on(self) -> bool:
        """Turn TV on (usually via Wake-on-LAN)"""
        pass

    @abstractmethod
    def power_off(self) -> bool:
        """Turn TV off/standby"""
        pass

    @abstractmethod
    def send_key(self, key: str, delay: float = 0.3) -> bool:
        """Send a remote control key press"""
        pass

    @abstractmethod
    def send_keys(self, keys: List[str], delay: float = 0.3) -> bool:
        """Send multiple key presses"""
        pass

    def volume_up(self, steps: int = 1) -> bool:
        """Increase volume"""
        for _ in range(steps):
            if not self.send_key('VOLUP'):
                return False
        return True

    def volume_down(self, steps: int = 1) -> bool:
        """Decrease volume"""
        for _ in range(steps):
            if not self.send_key('VOLDOWN'):
                return False
        return True

    def mute(self) -> bool:
        """Toggle mute"""
        return self.send_key('MUTE')

    def channel_up(self) -> bool:
        """Channel up"""
        return self.send_key('CHUP')

    def channel_down(self) -> bool:
        """Channel down"""
        return self.send_key('CHDOWN')

    # Optional methods with default implementations
    def get_volume(self) -> Optional[int]:
        """Get current volume level (if supported)"""
        return None

    def set_volume(self, level: int) -> bool:
        """Set volume to specific level (if supported)"""
        return False

    def get_mute_status(self) -> Optional[bool]:
        """Get mute status (if supported)"""
        return None

    def get_applications(self) -> List[dict]:
        """Get list of installed applications"""
        return []

    def launch_application(self, app_id: str) -> bool:
        """Launch an application"""
        return False


# Key mapping for standardized key names
# Each TV type maps these to their specific key codes
STANDARD_KEYS = {
    # Navigation
    'UP': 'Up arrow',
    'DOWN': 'Down arrow',
    'LEFT': 'Left arrow',
    'RIGHT': 'Right arrow',
    'ENTER': 'Enter/OK/Confirm',
    'BACK': 'Back/Return',
    'EXIT': 'Exit',
    'HOME': 'Home/Menu',

    # Power
    'POWER': 'Power toggle',
    'POWEROFF': 'Power off',

    # Volume
    'VOLUP': 'Volume up',
    'VOLDOWN': 'Volume down',
    'MUTE': 'Mute toggle',

    # Channels
    'CHUP': 'Channel up',
    'CHDOWN': 'Channel down',

    # Numbers
    '0': 'Number 0',
    '1': 'Number 1',
    '2': 'Number 2',
    '3': 'Number 3',
    '4': 'Number 4',
    '5': 'Number 5',
    '6': 'Number 6',
    '7': 'Number 7',
    '8': 'Number 8',
    '9': 'Number 9',

    # Playback
    'PLAY': 'Play',
    'PAUSE': 'Pause',
    'STOP': 'Stop',
    'REWIND': 'Rewind',
    'FASTFORWARD': 'Fast forward',
    'RECORD': 'Record',

    # Colors
    'RED': 'Red button',
    'GREEN': 'Green button',
    'YELLOW': 'Yellow button',
    'BLUE': 'Blue button',

    # Misc
    'INFO': 'Info/Guide',
    'SOURCE': 'Source/Input',
    'GUIDE': 'TV Guide',
    'TOOLS': 'Tools/Options',
}
