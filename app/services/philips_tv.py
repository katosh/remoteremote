"""
Philips TV Service - Implementation for Philips Android TVs
"""
import socket
from typing import Optional, List, Tuple, Callable

from .base_tv import BaseTVService, TVInfo

try:
    from philipstv import PhilipsTVRemote, InputKeyValue
    from philipstv.exceptions import PhilipsTVError
    PHILIPS_AVAILABLE = True
except ImportError:
    PHILIPS_AVAILABLE = False
    PhilipsTVRemote = None
    InputKeyValue = None
    PhilipsTVError = Exception


# Map standard keys to Philips InputKeyValue
# Keys can come with or without KEY_ prefix from Samsung-style remotes
PHILIPS_KEY_MAP = {
    # Navigation
    'UP': 'CURSOR_UP',
    'DOWN': 'CURSOR_DOWN',
    'LEFT': 'CURSOR_LEFT',
    'RIGHT': 'CURSOR_RIGHT',
    'ENTER': 'CONFIRM',
    'RETURN': 'BACK',  # Samsung uses RETURN for back
    'BACK': 'BACK',
    'EXIT': 'BACK',  # Philips uses BACK for exit
    'HOME': 'HOME',
    'MENU': 'HOME',  # Map Samsung MENU to Philips HOME

    # Power
    'POWER': 'STANDBY',
    'POWEROFF': 'STANDBY',

    # Volume
    'VOLUP': 'VOLUME_UP',
    'VOLDOWN': 'VOLUME_DOWN',
    'MUTE': 'MUTE',

    # Channels
    'CHUP': 'CHANNEL_STEP_UP',
    'CHDOWN': 'CHANNEL_STEP_DOWN',
    'CHLIST': 'CHANNEL_STEP_UP',  # No direct equivalent, use channel up
    'PRECH': 'PREVIOUS',  # Previous channel

    # Numbers
    '0': 'DIGIT_0',
    '1': 'DIGIT_1',
    '2': 'DIGIT_2',
    '3': 'DIGIT_3',
    '4': 'DIGIT_4',
    '5': 'DIGIT_5',
    '6': 'DIGIT_6',
    '7': 'DIGIT_7',
    '8': 'DIGIT_8',
    '9': 'DIGIT_9',

    # Playback
    'PLAY': 'PLAY_PAUSE',
    'PAUSE': 'PAUSE',
    'STOP': 'STOP',
    'REWIND': 'REWIND',
    'FF': 'FAST_FORWARD',  # Samsung uses FF
    'FASTFORWARD': 'FAST_FORWARD',
    'RECORD': 'RECORD',

    # Colors
    'RED': 'RED',
    'GREEN': 'GREEN',
    'YELLOW': 'YELLOW',
    'BLUE': 'BLUE',

    # Misc
    'INFO': 'INFO',
    'SOURCE': 'SOURCE',
    'HDMI': 'SOURCE',
    'GUIDE': 'WATCH_TV',
    'TOOLS': 'OPTIONS',
    'CAPTION': 'SUBTITLE',  # Samsung uses CAPTION for subtitles
    'AD': 'ADJUST',  # Audio description -> Adjust

    # Philips-specific keys (direct passthrough)
    'AMBILIGHT': 'AMBILIGHT_ON_OFF',
    'SUBTITLE': 'SUBTITLE',
    'TELETEXT': 'TELETEXT',
    'ONLINE': 'ONLINE',
    'FIND': 'FIND',
    'OPTIONS': 'OPTIONS',
    'ADJUST': 'ADJUST',
    'WATCH_TV': 'WATCH_TV',
    'TV': 'WATCH_TV',
}


class PhilipsTVService(BaseTVService):
    """Philips Android TV implementation"""

    def __init__(self, ip: str, mac: Optional[str] = None,
                 credentials: Optional[Tuple[str, str]] = None):
        super().__init__(ip, mac)
        self._credentials = credentials
        self._remote: Optional[PhilipsTVRemote] = None
        self._last_info: Optional[TVInfo] = None

        if not PHILIPS_AVAILABLE:
            raise ImportError("philipstv package is not installed")

        self._init_remote()

    def _init_remote(self):
        """Initialize the PhilipsTVRemote instance"""
        try:
            if self._credentials:
                self._remote = PhilipsTVRemote.new(self.ip, self._credentials)
            else:
                self._remote = PhilipsTVRemote.new(self.ip)
        except Exception as e:
            print(f"[Philips TV] Error initializing remote: {e}", flush=True)
            self._remote = None

    @property
    def tv_type(self) -> str:
        return 'philips'

    @property
    def is_paired(self) -> bool:
        return self._credentials is not None and len(self._credentials) == 2

    @property
    def credentials(self) -> Optional[Tuple[str, str]]:
        """Get stored credentials (id, key)"""
        return self._credentials

    def pair(self, pin_callback: Optional[Callable[[], str]] = None, **kwargs) -> bool:
        """
        Pair with Philips TV.

        Args:
            pin_callback: Function that returns the PIN displayed on TV

        Returns:
            True if pairing successful, credentials stored in self._credentials
        """
        if not self._remote:
            self._init_remote()

        if not self._remote:
            return False

        if not pin_callback:
            raise ValueError("Philips TV pairing requires a PIN callback function")

        try:
            print(f"[Philips TV] Starting pairing with {self.ip}...", flush=True)
            self._credentials = self._remote.pair(pin_callback)
            print(f"[Philips TV] Pairing successful!", flush=True)
            # Reinitialize with credentials
            self._init_remote()
            return True
        except Exception as e:
            print(f"[Philips TV] Pairing failed: {e}", flush=True)
            return False

    def ping(self, timeout: float = 2.0) -> bool:
        """Quick check if TV is reachable via TCP connection to API port"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((self.ip, 1926))  # Philips API port
            sock.close()
            return result == 0
        except Exception:
            return False

    def get_info(self) -> Optional[TVInfo]:
        """Get TV information"""
        if not self._remote or not self.is_paired:
            return None

        # Quick ping check first to avoid long timeout
        if not self.ping(timeout=1.0):
            print(f"[Philips TV] TV not reachable, skipping get_info", flush=True)
            return None

        try:
            # Try to get power state as a basic info check
            power = self._remote.get_power()
            power_state = 'on' if power else 'standby'

            info = TVInfo(
                name="Philips TV",
                model="Android TV",
                ip=self.ip,
                mac=self.mac,
                power_state=power_state
            )
            self._last_info = info
            return info
        except Exception as e:
            print(f"[Philips TV] Error getting info: {e}", flush=True)
            return None

    def power_on(self) -> bool:
        """Turn TV on"""
        if not self._remote or not self.is_paired:
            return False

        try:
            self._remote.set_power(True)
            return True
        except Exception as e:
            print(f"[Philips TV] Error powering on: {e}", flush=True)
            return False

    def power_off(self) -> bool:
        """Turn TV off/standby"""
        if not self._remote or not self.is_paired:
            return False

        try:
            self._remote.set_power(False)
            return True
        except Exception as e:
            print(f"[Philips TV] Error powering off: {e}", flush=True)
            return False

    def send_key(self, key: str, delay: float = 0.3) -> bool:
        """Send a remote control key press"""
        if not self._remote or not self.is_paired:
            print(f"[Philips TV] Cannot send key - not paired or no remote", flush=True)
            return False

        # Strip KEY_ prefix if present (Samsung-style keys)
        clean_key = key.upper()
        if clean_key.startswith('KEY_'):
            clean_key = clean_key[4:]

        # Map standard key to Philips key
        philips_key = PHILIPS_KEY_MAP.get(clean_key, clean_key)

        try:
            key_value = getattr(InputKeyValue, philips_key, None)
            if key_value is None:
                print(f"[Philips TV] Unknown key: {key} -> {clean_key} -> {philips_key}", flush=True)
                return False

            self._remote.input_key(key_value)
            return True
        except Exception as e:
            print(f"[Philips TV] Error sending key {key}: {e}", flush=True)
            return False

    def send_keys(self, keys: List[str], delay: float = 0.3) -> bool:
        """Send multiple key presses"""
        import time
        success = True
        for key in keys:
            if not self.send_key(key, delay):
                success = False
            if delay > 0:
                time.sleep(delay)
        return success

    def get_volume(self) -> Optional[int]:
        """Get current volume level"""
        if not self._remote or not self.is_paired:
            return None

        try:
            volume = self._remote.get_volume()
            return volume.current if hasattr(volume, 'current') else int(volume)
        except Exception as e:
            print(f"[Philips TV] Error getting volume: {e}", flush=True)
            return None

    def set_volume(self, level: int) -> bool:
        """Set volume to specific level"""
        if not self._remote or not self.is_paired:
            return False

        try:
            self._remote.set_volume(level)
            return True
        except Exception as e:
            print(f"[Philips TV] Error setting volume: {e}", flush=True)
            return False

    def get_applications(self) -> List[dict]:
        """Get list of installed applications"""
        if not self._remote or not self.is_paired:
            return []

        try:
            apps = self._remote.get_applications()
            return [{'id': app.id, 'name': app.label} for app in apps]
        except Exception as e:
            print(f"[Philips TV] Error getting applications: {e}", flush=True)
            return []

    def launch_application(self, app_name: str) -> bool:
        """Launch an application by name"""
        if not self._remote or not self.is_paired:
            return False

        try:
            self._remote.launch_application(app_name)
            return True
        except Exception as e:
            print(f"[Philips TV] Error launching app {app_name}: {e}", flush=True)
            return False

    def get_ambilight_power(self) -> Optional[bool]:
        """Get Ambilight power state"""
        if not self._remote or not self.is_paired:
            return None

        try:
            return self._remote.get_ambilight_power()
        except Exception:
            return None

    def set_ambilight_power(self, on: bool) -> bool:
        """Set Ambilight power state"""
        if not self._remote or not self.is_paired:
            return False

        try:
            self._remote.set_ambilight_power(on)
            return True
        except Exception as e:
            print(f"[Philips TV] Error setting ambilight: {e}", flush=True)
            return False


def discover_philips_tvs(timeout: int = 5) -> List[dict]:
    """
    Discover Philips TVs on the local network.

    Uses SSDP to find Philips TVs.
    """
    discovered = []

    # SSDP Multicast
    ssdp_addr = '239.255.255.250'
    ssdp_port = 1900

    # Search for Philips TVs
    ssdp_request = (
        'M-SEARCH * HTTP/1.1\r\n'
        f'HOST: {ssdp_addr}:{ssdp_port}\r\n'
        'MAN: "ssdp:discover"\r\n'
        f'MX: {timeout}\r\n'
        'ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n'
        '\r\n'
    )

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        sock.sendto(ssdp_request.encode(), (ssdp_addr, ssdp_port))

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                response = data.decode('utf-8', errors='ignore')

                if 'philips' in response.lower():
                    tv_info = {
                        'ip': addr[0],
                        'type': 'philips',
                        'source': 'ssdp'
                    }
                    if tv_info not in discovered:
                        discovered.append(tv_info)

            except socket.timeout:
                break

        sock.close()

    except Exception as e:
        print(f"[Philips Discovery] Error: {e}", flush=True)

    # Also try direct API check on common IPs
    from .discovery import _get_local_ips
    for local_ip in _get_local_ips():
        parts = local_ip.split('.')
        if len(parts) == 4:
            subnet = '.'.join(parts[:3])
            for last_octet in [1, 100, 101, 102, 103, 104, 105]:
                ip = f'{subnet}.{last_octet}'
                if ip not in [d['ip'] for d in discovered]:
                    if _check_philips_api(ip):
                        discovered.append({
                            'ip': ip,
                            'type': 'philips',
                            'source': 'scan'
                        })

    return discovered


def _check_philips_api(ip: str, timeout: int = 2) -> bool:
    """Check if Philips TV API responds on given IP"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, 1926))
        sock.close()
        return result == 0
    except Exception:
        return False
