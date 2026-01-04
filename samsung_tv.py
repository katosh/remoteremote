#!/usr/bin/env python3
"""
Samsung Smart TV Remote Control Library

Provides full control over Samsung Smart TVs (2016+) via WebSocket API.
Uses secure WebSocket (port 8002) with token-based authentication.
"""

import json
import base64
import time
import os
import struct
import socket
import ssl
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass
from enum import Enum


class Key(str, Enum):
    """All available Samsung TV remote control keys"""

    # Power
    POWER = "KEY_POWER"
    POWER_OFF = "KEY_POWEROFF"

    # Navigation
    UP = "KEY_UP"
    DOWN = "KEY_DOWN"
    LEFT = "KEY_LEFT"
    RIGHT = "KEY_RIGHT"
    ENTER = "KEY_ENTER"
    RETURN = "KEY_RETURN"
    EXIT = "KEY_EXIT"

    # Volume
    VOLUME_UP = "KEY_VOLUP"
    VOLUME_DOWN = "KEY_VOLDOWN"
    MUTE = "KEY_MUTE"

    # Channels
    CHANNEL_UP = "KEY_CHUP"
    CHANNEL_DOWN = "KEY_CHDOWN"
    CHANNEL_LIST = "KEY_CH_LIST"
    PREVIOUS_CHANNEL = "KEY_PRECH"

    # Numbers
    NUM_0 = "KEY_0"
    NUM_1 = "KEY_1"
    NUM_2 = "KEY_2"
    NUM_3 = "KEY_3"
    NUM_4 = "KEY_4"
    NUM_5 = "KEY_5"
    NUM_6 = "KEY_6"
    NUM_7 = "KEY_7"
    NUM_8 = "KEY_8"
    NUM_9 = "KEY_9"

    # Media Controls
    PLAY = "KEY_PLAY"
    PAUSE = "KEY_PAUSE"
    STOP = "KEY_STOP"
    REWIND = "KEY_REWIND"
    FAST_FORWARD = "KEY_FF"
    RECORD = "KEY_REC"

    # Color Buttons
    RED = "KEY_RED"
    GREEN = "KEY_GREEN"
    YELLOW = "KEY_YELLOW"
    BLUE = "KEY_BLUE"

    # Smart Features
    HOME = "KEY_HOME"
    MENU = "KEY_MENU"
    SOURCE = "KEY_SOURCE"
    GUIDE = "KEY_GUIDE"
    TOOLS = "KEY_TOOLS"
    INFO = "KEY_INFO"

    # Picture Controls
    PICTURE_SIZE = "KEY_PICTURE_SIZE"
    PIP_ONOFF = "KEY_PIP_ONOFF"
    PIP_SWAP = "KEY_PIP_SWAP"
    PIP_SIZE = "KEY_PIP_SIZE"
    PIP_CHUP = "KEY_PIP_CHUP"
    PIP_CHDOWN = "KEY_PIP_CHDOWN"

    # Audio
    AD = "KEY_AD"  # Audio Description
    AUDIO = "KEY_AUTO_ARC_RESET"

    # Teletext
    TTX_MIX = "KEY_TTX_MIX"
    TTX_SUBFACE = "KEY_TTX_SUBFACE"

    # Special
    CAPTION = "KEY_CAPTION"
    SLEEP = "KEY_SLEEP"
    ASPECT = "KEY_ASPECT"
    ESAVING = "KEY_ESAVING"
    AMBIENT = "KEY_AMBIENT"

    # Apps
    NETFLIX = "KEY_NETFLIX"
    AMAZON = "KEY_AMAZON"
    WWW = "KEY_WWW"

    # Extra Navigation
    PAGE_UP = "KEY_PAGEUP"
    PAGE_DOWN = "KEY_PAGEDOWN"


class App(str, Enum):
    """Common Samsung TV app IDs"""
    NETFLIX = "Netflix"
    YOUTUBE = "YouTube"
    AMAZON_PRIME = "Amazon Prime Video"
    DISNEY_PLUS = "Disney+"
    APPLE_TV = "Apple TV"
    SPOTIFY = "Spotify"
    BROWSER = "org.tizen.browser"
    SETTINGS = "com.samsung.tv.settings"
    SMART_HUB = "com.samsung.tv.smarthub"
    TV_PLUS = "com.samsung.tv.tvplus"


@dataclass
class TVInfo:
    """TV device information"""
    name: str
    model: str
    model_name: str
    ip: str
    mac: str
    power_state: str
    firmware: str
    os: str
    resolution: str
    uuid: str

    @classmethod
    def from_api_response(cls, data: Dict) -> 'TVInfo':
        device = data.get('device', {})
        return cls(
            name=data.get('name', 'Unknown'),
            model=device.get('model', 'Unknown'),
            model_name=device.get('modelName', 'Unknown'),
            ip=device.get('ip', 'Unknown'),
            mac=device.get('wifiMac', 'Unknown'),
            power_state=device.get('PowerState', 'Unknown'),
            firmware=device.get('firmwareVersion', 'Unknown'),
            os=device.get('OS', 'Unknown'),
            resolution=device.get('resolution', 'Unknown'),
            uuid=data.get('id', 'Unknown'),
        )


class SamsungUPnP:
    """
    UPnP interface for Samsung TV volume control.

    Uses SOAP protocol on port 9197 to get/set volume directly.
    This allows setting a specific volume value instead of just up/down.
    """

    UPNP_PORT = 9197
    UPNP_TIMEOUT = 2.0

    def __init__(self, ip: str):
        self.ip = ip

    def _soap_request(self, action: str, arguments: str, protocol: str = "RenderingControl") -> Optional[str]:
        """Send a SOAP request to the TV."""
        import http.client

        headers = {
            "SOAPAction": f'"urn:schemas-upnp-org:service:{protocol}:1#{action}"',
            "Content-Type": "text/xml; charset=utf-8",
        }

        body = f'''<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <s:Body>
        <u:{action} xmlns:u="urn:schemas-upnp-org:service:{protocol}:1">
            <InstanceID>0</InstanceID>
            {arguments}
        </u:{action}>
    </s:Body>
</s:Envelope>'''

        try:
            conn = http.client.HTTPConnection(self.ip, self.UPNP_PORT, timeout=self.UPNP_TIMEOUT)
            conn.request("POST", f"/upnp/control/{protocol}1", body, headers)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            conn.close()
            return data
        except Exception as e:
            return None

    def get_volume(self) -> Optional[int]:
        """Get current volume level (0-100)."""
        response = self._soap_request("GetVolume", "<Channel>Master</Channel>")
        if response is None:
            return None

        # Parse XML response to extract volume
        import re
        match = re.search(r'<CurrentVolume>(\d+)</CurrentVolume>', response)
        if match:
            return int(match.group(1))
        return None

    def set_volume(self, volume: int) -> bool:
        """Set volume level (0-100)."""
        volume = max(0, min(100, volume))
        response = self._soap_request(
            "SetVolume",
            f"<Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume>"
        )
        return response is not None

    def get_mute(self) -> Optional[bool]:
        """Get current mute status."""
        response = self._soap_request("GetMute", "<Channel>Master</Channel>")
        if response is None:
            return None

        import re
        match = re.search(r'<CurrentMute>(\d+)</CurrentMute>', response)
        if match:
            return int(match.group(1)) != 0
        return None

    def set_mute(self, muted: bool) -> bool:
        """Set mute status."""
        value = "1" if muted else "0"
        response = self._soap_request(
            "SetMute",
            f"<Channel>Master</Channel><DesiredMute>{value}</DesiredMute>"
        )
        return response is not None


class SamsungTV:
    """
    Samsung Smart TV Remote Control

    Usage:
        tv = SamsungTV("192.168.178.103")

        # First time - pair with TV (user must accept on TV screen)
        tv.pair()

        # Send commands
        tv.mute()
        tv.volume_up()
        tv.channel(5)
        tv.send_key(Key.HOME)

        # Power control
        tv.power_off()
        tv.power_on()  # Wake-on-LAN
    """

    def __init__(
        self,
        ip: str,
        port: int = 8002,
        app_name: str = "PiTVRemote",
        token_file: Optional[str] = None,
        mac: Optional[str] = None,
    ):
        self.ip = ip
        self.port = port
        self.app_name = app_name
        self.token_file = token_file or os.path.expanduser("~/.tv_token")
        self.mac = mac
        self._token: Optional[str] = None
        self._upnp = SamsungUPnP(ip)  # UPnP for volume control
        self._load_token()

    def _load_token(self) -> None:
        """Load token from file if exists"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file) as f:
                    self._token = f.read().strip()
                    if self._token:
                        print(f"[SamsungTV] Token loaded from {self.token_file}", flush=True)
                    else:
                        print(f"[SamsungTV] Token file exists but is empty: {self.token_file}", flush=True)
                        self._token = None
            else:
                print(f"[SamsungTV] No token file found at {self.token_file}", flush=True)
        except PermissionError as e:
            print(f"[SamsungTV] Permission denied reading token file: {e}", flush=True)
        except Exception as e:
            print(f"[SamsungTV] Error loading token: {e}", flush=True)

    def _save_token(self, token: str) -> None:
        """Save token to file"""
        self._token = token
        try:
            # Ensure directory exists
            token_dir = os.path.dirname(self.token_file)
            if token_dir and not os.path.exists(token_dir):
                os.makedirs(token_dir, exist_ok=True)
                print(f"[SamsungTV] Created token directory: {token_dir}", flush=True)

            with open(self.token_file, "w") as f:
                f.write(token)
            print(f"[SamsungTV] Token saved to {self.token_file}", flush=True)
        except PermissionError as e:
            print(f"[SamsungTV] Permission denied saving token: {e}", flush=True)
            print(f"[SamsungTV] Tip: Check that the user has write access to {self.token_file}", flush=True)
        except Exception as e:
            print(f"[SamsungTV] Error saving token: {e}", flush=True)

    @property
    def token(self) -> Optional[str]:
        return self._token

    @property
    def is_paired(self) -> bool:
        return self._token is not None

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context that accepts self-signed certs"""
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def _make_ws_frame(self, data: str) -> bytes:
        """Create a WebSocket text frame with masking"""
        data_bytes = data.encode('utf-8')
        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode

        length = len(data_bytes)
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('>Q', length))

        mask = os.urandom(4)
        frame.extend(mask)

        for i, b in enumerate(data_bytes):
            frame.append(b ^ mask[i % 4])

        return bytes(frame)

    def _parse_ws_frames(self, data: bytes) -> List[Dict]:
        """Parse WebSocket frames and extract JSON payloads"""
        results = []
        text = data.decode('utf-8', errors='replace')

        i = 0
        while i < len(text):
            if text[i] == '{':
                depth = 0
                start = i
                for j in range(i, len(text)):
                    if text[j] == '{':
                        depth += 1
                    elif text[j] == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                obj = json.loads(text[start:j+1])
                                results.append(obj)
                            except:
                                pass
                            i = j
                            break
                i += 1
            else:
                i += 1
        return results

    def _create_connection(self, timeout: int = 10) -> tuple:
        """Create WebSocket connection to TV"""
        context = self._get_ssl_context()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        ssock = context.wrap_socket(sock, server_hostname=self.ip)
        ssock.connect((self.ip, self.port))

        # Build path
        encoded_name = base64.b64encode(self.app_name.encode()).decode()
        path = f"/api/v2/channels/samsung.remote.control?name={encoded_name}"
        if self._token:
            path += f"&token={self._token}"

        # WebSocket handshake
        ws_key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {self.ip}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        ).encode()

        ssock.send(handshake)
        response = ssock.recv(4096)

        if b"101" not in response:
            raise ConnectionError(f"WebSocket handshake failed: {response[:200]}")

        return ssock, response

    def _rest_request(self, endpoint: str = "", method: str = "GET", port: int = 8001, timeout: float = 5.0, body: str = None, fire_and_forget: bool = False) -> Optional[Dict]:
        """
        Make a REST API request to the TV.

        Args:
            endpoint: API endpoint (e.g., "", "applications/Netflix")
            method: HTTP method (GET, POST, PUT, DELETE)
            port: Port number (8001 for REST API)
            timeout: Request timeout in seconds
            body: Optional request body
            fire_and_forget: If True, don't wait for response (for app launches that time out)
        """
        import http.client
        import urllib.parse

        try:
            if port == self.port:  # SSL port (8002)
                conn = http.client.HTTPSConnection(self.ip, port, timeout=timeout, context=self._get_ssl_context())
            else:
                conn = http.client.HTTPConnection(self.ip, port, timeout=timeout)

            url = f"/api/v2/{endpoint}"
            headers = {}
            if body:
                headers['Content-Type'] = 'text/plain'
                conn.request(method, url, body=body, headers=headers)
            else:
                conn.request(method, url)

            if fire_and_forget:
                # Don't wait for response - some TVs open apps but don't respond
                try:
                    conn.sock.settimeout(0.5)
                    response = conn.getresponse()
                    conn.close()
                    return {"status": "ok", "http_status": response.status}
                except:
                    conn.close()
                    return {"status": "ok", "fire_and_forget": True}

            response = conn.getresponse()
            status = response.status
            data = response.read().decode('utf-8')
            conn.close()

            # For app launch, various status codes indicate success
            # 200 OK, 201 Created, 204 No Content are all success
            if status in (200, 201, 204):
                try:
                    return json.loads(data) if data.strip() else {"status": "ok"}
                except json.JSONDecodeError:
                    return {"status": "ok", "raw": data}
            # Some Samsung TVs return other codes for app operations
            elif method == "POST" and status < 400:
                return {"status": "ok", "http_status": status}
            return None
        except Exception as e:
            if fire_and_forget:
                # For fire_and_forget, assume success on timeout
                return {"status": "ok", "fire_and_forget": True, "note": str(e)}
            return None

    def get_info(self) -> Optional[TVInfo]:
        """Get TV information via REST API"""
        # Try port 8001 first (REST API), then fall back to SSL port
        data = self._rest_request("", port=8001)
        if data is None:
            data = self._rest_request("", port=self.port)

        if data:
            # Also extract MAC if we don't have it
            if not self.mac:
                self.mac = data.get('device', {}).get('wifiMac')
            return TVInfo.from_api_response(data)
        return None

    def is_on(self) -> bool:
        """Check if TV is on (not in standby)"""
        info = self.get_info()
        if info:
            return info.power_state == "on"
        return False

    def ping(self, timeout: float = 2.0) -> bool:
        """Check if TV is reachable on the network."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((self.ip, 8001))
            sock.close()
            return result == 0
        except Exception:
            return False

    # REST API for App Control

    def get_app_status(self, app_id: str) -> Optional[Dict]:
        """Get status of an installed app."""
        return self._rest_request(f"applications/{app_id}")

    def run_app(self, app_id: str) -> bool:
        """Launch an app by ID (e.g., 'Netflix', 'YouTube')."""
        result = self._rest_request(f"applications/{app_id}", method="POST")
        return result is not None

    def close_app(self, app_id: str) -> bool:
        """Close a running app by ID."""
        result = self._rest_request(f"applications/{app_id}", method="DELETE")
        return result is not None

    def install_app(self, app_id: str) -> bool:
        """Install an app from the store."""
        result = self._rest_request(f"applications/{app_id}", method="PUT")
        return result is not None

    def get_installed_apps(self) -> Optional[List[Dict]]:
        """Get list of installed apps (requires WebSocket connection)."""
        # This requires WebSocket - not available via REST
        # TODO: Implement via WebSocket
        return None

    def pair(self, timeout: int = 60) -> bool:
        """
        Pair with TV - user must accept on TV screen.

        Returns True if pairing successful, False otherwise.
        """
        try:
            ssock, initial_response = self._create_connection(timeout=timeout)

            # Check initial response
            frames = self._parse_ws_frames(initial_response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.connect':
                    token = frame.get('data', {}).get('token')
                    if token:
                        self._save_token(token)
                        ssock.close()
                        return True

            # Wait for token
            start_time = time.time()
            all_data = initial_response

            while time.time() - start_time < timeout:
                try:
                    ssock.settimeout(1)
                    data = ssock.recv(4096)
                    if data:
                        all_data += data
                        frames = self._parse_ws_frames(all_data)
                        for frame in frames:
                            if frame.get('event') == 'ms.channel.connect':
                                token = frame.get('data', {}).get('token')
                                if token:
                                    self._save_token(token)
                                    ssock.close()
                                    return True
                except socket.timeout:
                    pass

            ssock.close()
            return False

        except Exception as e:
            raise ConnectionError(f"Pairing failed: {e}")

    def send_key(self, key: Union[Key, str], delay: float = 0.3) -> bool:
        """
        Send a remote control key to the TV.

        Args:
            key: Key enum value or string (e.g., Key.MUTE or "KEY_MUTE")
            delay: Delay after sending key (seconds)

        Returns:
            True if successful, False otherwise
        """
        if not self._token:
            raise RuntimeError("Not paired - call pair() first")

        key_str = key.value if isinstance(key, Key) else key

        try:
            ssock, response = self._create_connection()

            # Check authorization
            frames = self._parse_ws_frames(response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.unauthorized':
                    ssock.close()
                    raise PermissionError("Unauthorized - token may be expired")

            time.sleep(0.2)

            # Send key
            payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Click",
                    "DataOfCmd": key_str,
                    "Option": "false",
                    "TypeOfRemote": "SendRemoteKey"
                }
            })

            frame = self._make_ws_frame(payload)
            ssock.send(frame)

            time.sleep(delay)
            ssock.close()
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to send key: {e}")

    def send_keys(self, keys: List[Union[Key, str]], delay: float = 0.3) -> bool:
        """Send multiple keys in sequence"""
        for key in keys:
            self.send_key(key, delay)
        return True

    def hold_key(self, key: Union[Key, str], seconds: float = 1.0) -> bool:
        """
        Press and hold a key for specified duration.

        Useful for volume control (hold to rapidly change) or navigation.
        """
        if not self._token:
            raise RuntimeError("Not paired - call pair() first")

        key_str = key.value if isinstance(key, Key) else key

        try:
            ssock, response = self._create_connection()

            frames = self._parse_ws_frames(response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.unauthorized':
                    ssock.close()
                    raise PermissionError("Unauthorized - token may be expired")

            time.sleep(0.2)

            # Press key
            press_payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Press",
                    "DataOfCmd": key_str,
                    "Option": "false",
                    "TypeOfRemote": "SendRemoteKey"
                }
            })
            ssock.send(self._make_ws_frame(press_payload))

            # Hold for duration
            time.sleep(seconds)

            # Release key
            release_payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Release",
                    "DataOfCmd": key_str,
                    "Option": "false",
                    "TypeOfRemote": "SendRemoteKey"
                }
            })
            ssock.send(self._make_ws_frame(release_payload))

            time.sleep(0.1)
            ssock.close()
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to hold key: {e}")

    def send_text(self, text: str) -> bool:
        """
        Send text input to the TV (for search fields, etc).
        """
        if not self._token:
            raise RuntimeError("Not paired - call pair() first")

        try:
            ssock, response = self._create_connection()

            frames = self._parse_ws_frames(response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.unauthorized':
                    ssock.close()
                    raise PermissionError("Unauthorized - token may be expired")

            time.sleep(0.2)

            # Send text as base64
            text_b64 = base64.b64encode(text.encode()).decode()
            payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": text_b64,
                    "DataOfCmd": "base64",
                    "TypeOfRemote": "SendInputString"
                }
            })
            ssock.send(self._make_ws_frame(payload))

            time.sleep(0.2)

            # Send input end
            end_payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "TypeOfRemote": "SendInputEnd"
                }
            })
            ssock.send(self._make_ws_frame(end_payload))

            time.sleep(0.1)
            ssock.close()
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to send text: {e}")

    def move_cursor(self, x: int, y: int, duration: int = 0) -> bool:
        """
        Move the cursor/pointer to a specific position.

        Args:
            x: X coordinate
            y: Y coordinate
            duration: Animation duration in ms
        """
        if not self._token:
            raise RuntimeError("Not paired - call pair() first")

        try:
            ssock, response = self._create_connection()

            frames = self._parse_ws_frames(response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.unauthorized':
                    ssock.close()
                    raise PermissionError("Unauthorized - token may be expired")

            time.sleep(0.2)

            payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Move",
                    "Position": {"x": x, "y": y, "Time": str(duration)},
                    "TypeOfRemote": "ProcessMouseDevice"
                }
            })
            ssock.send(self._make_ws_frame(payload))

            time.sleep(0.1)
            ssock.close()
            return True

        except Exception as e:
            raise RuntimeError(f"Failed to move cursor: {e}")

    def open_browser(self, url: str) -> bool:
        """
        Open the TV's built-in browser with the specified URL.

        Tries multiple methods since Samsung changed APIs across TV generations:
        1. REST API (works on many 2019+ TVs)
        2. ms.application.start WebSocket method (Control Channel)
        3. ed.apps.launch WebSocket method (Remote Channel)

        Also tries multiple browser app IDs as these vary by TV model/year.
        """
        # Known Samsung browser app IDs (varies by TV model/year)
        browser_app_ids = [
            "org.tizen.browser",           # Standard Tizen browser
            "com.samsung.tv.inapp-browser", # In-app browser
            "Internet",                     # Some models use this name
        ]

        errors = []

        # Method 1: Try REST API to launch browser (most reliable on 2019+ TVs)
        # Use fire_and_forget because some TVs don't respond but still open the browser
        browser_launched_via_rest = False
        for app_id in browser_app_ids:
            try:
                print(f"[SamsungTV] Trying REST API with app_id={app_id}", flush=True)
                result = self._rest_request(f"applications/{app_id}", method="POST", port=8001, fire_and_forget=True)
                if result is not None:
                    print(f"[SamsungTV] REST API launch sent for {app_id}", flush=True)
                    browser_launched_via_rest = True
                    time.sleep(0.5)  # Give browser time to start
                    break
            except Exception as e:
                errors.append(f"REST {app_id}: {e}")

        # Method 2 & 3: WebSocket methods (require token)
        if not self._token:
            print(f"[SamsungTV] No token - skipping WebSocket methods", flush=True)
            raise RuntimeError(f"Failed to open browser. Errors: {errors}")

        try:
            ssock, response = self._create_connection()

            frames = self._parse_ws_frames(response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.unauthorized':
                    ssock.close()
                    raise PermissionError("Unauthorized - token may be expired")

            time.sleep(0.2)

            # Method 2: Try ms.application.start (Control Channel method)
            for app_id in browser_app_ids:
                try:
                    print(f"[SamsungTV] Trying ms.application.start with app_id={app_id}", flush=True)
                    payload = json.dumps({
                        "method": "ms.application.start",
                        "params": {
                            "id": app_id,
                            "metaTag": url
                        }
                    })
                    ssock.send(self._make_ws_frame(payload))
                    time.sleep(0.5)

                    # Check for response
                    try:
                        ssock.settimeout(1)
                        resp_data = ssock.recv(4096)
                        resp_frames = self._parse_ws_frames(resp_data)
                        for rf in resp_frames:
                            if rf.get('event') == 'ms.application.start':
                                print(f"[SamsungTV] ms.application.start succeeded", flush=True)
                                ssock.close()
                                return True
                    except socket.timeout:
                        pass  # No response, try next method
                except Exception as e:
                    errors.append(f"ms.application.start {app_id}: {e}")

            # Method 3: Try ed.apps.launch with different action types
            action_types = ["NATIVE_LAUNCH", "DEEP_LINK"]
            for app_id in browser_app_ids:
                for action_type in action_types:
                    try:
                        print(f"[SamsungTV] Trying ed.apps.launch with app_id={app_id}, action_type={action_type}", flush=True)
                        payload = json.dumps({
                            "method": "ms.channel.emit",
                            "params": {
                                "event": "ed.apps.launch",
                                "to": "host",
                                "data": {
                                    "appId": app_id,
                                    "action_type": action_type,
                                    "metaTag": url
                                }
                            }
                        })
                        ssock.send(self._make_ws_frame(payload))
                        time.sleep(0.3)
                    except Exception as e:
                        errors.append(f"ed.apps.launch {app_id}/{action_type}: {e}")

            time.sleep(0.3)
            ssock.close()

            # We sent the commands - can't know for sure if they worked
            print(f"[SamsungTV] Sent all browser launch commands", flush=True)
            return True

        except Exception as e:
            errors.append(f"WebSocket: {e}")
            raise RuntimeError(f"Failed to open browser: {errors}")

    def open_browser_with_text(self, url: str, wait_time: float = 3.0) -> bool:
        """
        Open browser and navigate to URL by typing it.

        Workaround for 2020+ Samsung TVs where URL can't be passed via API.
        This method:
        1. Launches the browser app
        2. Waits for it to load
        3. Opens address bar and types the URL
        4. Presses Enter to navigate

        Args:
            url: The URL to navigate to
            wait_time: Seconds to wait for browser to load (default: 3)
        """
        print(f"[SamsungTV] Opening browser with text input workaround", flush=True)

        # Step 1: Launch browser (fire_and_forget because TV may not respond)
        browser_launched = False
        for app_id in ["org.tizen.browser", "com.samsung.tv.inapp-browser", "Internet"]:
            try:
                result = self._rest_request(f"applications/{app_id}", method="POST", port=8001, fire_and_forget=True)
                if result is not None:
                    print(f"[SamsungTV] Browser launch sent via REST: {app_id}", flush=True)
                    browser_launched = True
                    break
            except Exception:
                pass

        if not browser_launched:
            # Try WebSocket launch without URL
            try:
                ssock, response = self._create_connection()
                payload = json.dumps({
                    "method": "ms.channel.emit",
                    "params": {
                        "event": "ed.apps.launch",
                        "to": "host",
                        "data": {
                            "appId": "org.tizen.browser",
                            "action_type": "NATIVE_LAUNCH"
                        }
                    }
                })
                ssock.send(self._make_ws_frame(payload))
                time.sleep(0.3)
                ssock.close()
                browser_launched = True
                print(f"[SamsungTV] Browser launched via WebSocket", flush=True)
            except Exception as e:
                print(f"[SamsungTV] Failed to launch browser: {e}", flush=True)
                return False

        # Step 2: Wait for browser to load
        print(f"[SamsungTV] Waiting {wait_time}s for browser to load...", flush=True)
        time.sleep(wait_time)

        # Step 3: Try to focus address bar and type URL
        # Samsung browser address bar focus varies by model - try multiple methods
        try:
            # The Samsung browser typically shows the homepage or last page
            # Address bar is at the top - we need to navigate there and activate it

            # Method 1: Try pressing UP multiple times to reach address bar
            print(f"[SamsungTV] Navigating to address bar (UP x3)...", flush=True)
            for _ in range(3):
                self.send_key(Key.UP)
                time.sleep(0.3)

            # Press ENTER to activate/focus the address bar
            print(f"[SamsungTV] Activating address bar (ENTER)...", flush=True)
            self.send_key(Key.ENTER)
            time.sleep(0.8)

            # Step 4: Type the URL
            print(f"[SamsungTV] Typing URL: {url}", flush=True)
            self.send_text(url)
            time.sleep(0.5)

            # Step 5: Press Enter to navigate
            print(f"[SamsungTV] Pressing Enter to navigate", flush=True)
            self.send_key(Key.ENTER)

            return True

        except Exception as e:
            print(f"[SamsungTV] Failed to type URL: {e}", flush=True)
            return False

    def open_browser_manual_entry(self, url: str, wait_time: float = 3.0,
                                   up_presses: int = 3, extra_enter: bool = True) -> bool:
        """
        Open browser and navigate to URL with configurable key sequence.

        This is a customizable version for testing different key sequences
        to focus the address bar on different Samsung TV models.

        Args:
            url: The URL to navigate to
            wait_time: Seconds to wait for browser to load
            up_presses: Number of UP key presses to reach address bar
            extra_enter: Whether to press ENTER before typing (to activate input)
        """
        print(f"[SamsungTV] Opening browser with manual entry (up={up_presses}, enter={extra_enter})", flush=True)

        # Launch browser via REST API (fire_and_forget because TV may not respond)
        try:
            result = self._rest_request("applications/org.tizen.browser", method="POST", port=8001, fire_and_forget=True)
            print(f"[SamsungTV] Browser launch sent", flush=True)
        except Exception as e:
            print(f"[SamsungTV] Browser launch error: {e}", flush=True)
            return False

        # Wait for browser to load
        print(f"[SamsungTV] Waiting {wait_time}s...", flush=True)
        time.sleep(wait_time)

        try:
            # Navigate to address bar
            print(f"[SamsungTV] Pressing UP {up_presses} times...", flush=True)
            for i in range(up_presses):
                self.send_key(Key.UP)
                time.sleep(0.3)

            if extra_enter:
                print(f"[SamsungTV] Pressing ENTER to activate...", flush=True)
                self.send_key(Key.ENTER)
                time.sleep(0.8)

            # Type URL
            print(f"[SamsungTV] Typing URL...", flush=True)
            self.send_text(url)
            time.sleep(0.5)

            # Navigate
            print(f"[SamsungTV] Pressing ENTER to navigate...", flush=True)
            self.send_key(Key.ENTER)

            return True

        except Exception as e:
            print(f"[SamsungTV] Error: {e}", flush=True)
            return False

    def click(self, x: int, y: int) -> bool:
        """
        Click at specific screen coordinates.

        Args:
            x: X coordinate
            y: Y coordinate
        """
        if not self._token:
            raise RuntimeError("Not paired - call pair() first")

        try:
            ssock, response = self._create_connection()

            frames = self._parse_ws_frames(response)
            for frame in frames:
                if frame.get('event') == 'ms.channel.unauthorized':
                    ssock.close()
                    raise PermissionError("Unauthorized")

            time.sleep(0.1)

            # Move to position
            move_payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "Move",
                    "Position": {"x": x, "y": y, "Time": "0"},
                    "TypeOfRemote": "ProcessMouseDevice"
                }
            })
            ssock.send(self._make_ws_frame(move_payload))
            time.sleep(0.1)

            # Click
            click_payload = json.dumps({
                "method": "ms.remote.control",
                "params": {
                    "Cmd": "LeftClick",
                    "TypeOfRemote": "ProcessMouseDevice"
                }
            })
            ssock.send(self._make_ws_frame(click_payload))

            time.sleep(0.1)
            ssock.close()
            return True

        except Exception as e:
            print(f"[SamsungTV] Click failed: {e}", flush=True)
            return False

    def open_browser_with_click(self, url: str, wait_time: float = 3.0,
                                 address_bar_x: int = 960, address_bar_y: int = 50) -> bool:
        """
        Open browser and navigate to URL by clicking on the address bar.

        Uses mouse click at coordinates instead of keyboard navigation.
        Default coordinates assume 1920x1080 resolution with address bar at top center.

        Args:
            url: The URL to navigate to
            wait_time: Seconds to wait for browser to load
            address_bar_x: X coordinate of address bar (default: center of 1920 screen)
            address_bar_y: Y coordinate of address bar (default: near top)
        """
        print(f"[SamsungTV] Opening browser with click method", flush=True)

        # Launch browser via REST API (fire_and_forget because TV may not respond)
        try:
            self._rest_request("applications/org.tizen.browser", method="POST", port=8001, fire_and_forget=True)
            print(f"[SamsungTV] Browser launch sent", flush=True)
        except Exception as e:
            print(f"[SamsungTV] Browser launch error: {e}", flush=True)
            return False

        # Wait for browser to load
        print(f"[SamsungTV] Waiting {wait_time}s...", flush=True)
        time.sleep(wait_time)

        try:
            # Click on address bar
            print(f"[SamsungTV] Clicking on address bar at ({address_bar_x}, {address_bar_y})...", flush=True)
            self.click(address_bar_x, address_bar_y)
            time.sleep(0.8)

            # Type URL
            print(f"[SamsungTV] Typing URL...", flush=True)
            self.send_text(url)
            time.sleep(0.5)

            # Press Enter
            print(f"[SamsungTV] Pressing ENTER...", flush=True)
            self.send_key(Key.ENTER)

            return True

        except Exception as e:
            print(f"[SamsungTV] Error: {e}", flush=True)
            return False

    # Convenience methods

    def power_off(self) -> bool:
        """Turn TV off"""
        return self.send_key(Key.POWER)

    def power_on(self, close_menu: bool = False, wait_time: float = 5.0) -> bool:
        """
        Turn TV on via Wake-on-LAN.

        Args:
            close_menu: If True, send EXIT key after TV wakes up to close Smart Hub
            wait_time: Seconds to wait before closing menu (TV needs time to boot)

        Note: To permanently disable Smart Hub on startup, go to:
        Settings → General & Privacy → Start Screen Options → Disable "Start with Smart Hub Home"
        """
        if not self.mac:
            info = self.get_info()
            if not info or not self.mac:
                raise RuntimeError("MAC address not available")

        mac = self.mac.replace(":", "").replace("-", "")
        magic = b'\xff' * 6 + bytes.fromhex(mac) * 16

        # Calculate subnet broadcast address from TV IP (assumes /24 subnet)
        ip_parts = self.ip.split('.')
        subnet_broadcast = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.255"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Send multiple packets for reliability (UDP can drop packets)
        # Try global broadcast, subnet broadcast, and direct to TV IP
        targets = [
            ('255.255.255.255', 9),   # Global broadcast
            (subnet_broadcast, 9),     # Subnet-directed broadcast
            (self.ip, 9),              # Direct to TV (unicast)
        ]

        for i in range(3):
            for target in targets:
                try:
                    sock.sendto(magic, target)
                except Exception:
                    pass  # Some targets may fail, that's ok
            if i < 2:
                time.sleep(0.1)

        sock.close()

        if close_menu:
            time.sleep(wait_time)
            self.close_menu()

        return True

    def close_menu(self) -> bool:
        """
        Close Smart Hub / Home menu by sending EXIT key.

        Useful after Wake-on-LAN if TV is set to start with Smart Hub.
        """
        try:
            return self.send_key(Key.EXIT)
        except Exception:
            return False

    def mute(self) -> bool:
        """Toggle mute"""
        return self.send_key(Key.MUTE)

    def volume_up(self, steps: int = 1) -> bool:
        """Increase volume"""
        for _ in range(steps):
            self.send_key(Key.VOLUME_UP)
        return True

    def volume_down(self, steps: int = 1) -> bool:
        """Decrease volume"""
        for _ in range(steps):
            self.send_key(Key.VOLUME_DOWN)
        return True

    # UPnP-based volume control (direct value setting)

    def get_volume(self) -> Optional[int]:
        """Get current volume level (0-100) via UPnP"""
        return self._upnp.get_volume()

    def set_volume(self, volume: int) -> bool:
        """Set volume to specific level (0-100) via UPnP"""
        return self._upnp.set_volume(volume)

    def get_mute_status(self) -> Optional[bool]:
        """Get current mute status via UPnP"""
        return self._upnp.get_mute()

    def set_mute(self, muted: bool) -> bool:
        """Set mute status via UPnP"""
        return self._upnp.set_mute(muted)

    def channel_up(self) -> bool:
        """Next channel"""
        return self.send_key(Key.CHANNEL_UP)

    def channel_down(self) -> bool:
        """Previous channel"""
        return self.send_key(Key.CHANNEL_DOWN)

    def channel(self, number: int) -> bool:
        """Go to specific channel by number"""
        keys = [getattr(Key, f"NUM_{d}") for d in str(number)]
        self.send_keys(keys, delay=0.2)
        time.sleep(0.5)
        return self.send_key(Key.ENTER)

    def home(self) -> bool:
        """Open Smart Hub / Home"""
        return self.send_key(Key.HOME)

    def back(self) -> bool:
        """Go back / Return"""
        return self.send_key(Key.RETURN)

    def exit(self) -> bool:
        """Exit current menu/app"""
        return self.send_key(Key.EXIT)

    def up(self) -> bool:
        return self.send_key(Key.UP)

    def down(self) -> bool:
        return self.send_key(Key.DOWN)

    def left(self) -> bool:
        return self.send_key(Key.LEFT)

    def right(self) -> bool:
        return self.send_key(Key.RIGHT)

    def enter(self) -> bool:
        return self.send_key(Key.ENTER)

    def play(self) -> bool:
        return self.send_key(Key.PLAY)

    def pause(self) -> bool:
        return self.send_key(Key.PAUSE)

    def stop(self) -> bool:
        return self.send_key(Key.STOP)

    def rewind(self) -> bool:
        return self.send_key(Key.REWIND)

    def fast_forward(self) -> bool:
        return self.send_key(Key.FAST_FORWARD)

    def info(self) -> bool:
        return self.send_key(Key.INFO)

    def guide(self) -> bool:
        return self.send_key(Key.GUIDE)

    def source(self) -> bool:
        return self.send_key(Key.SOURCE)

    def menu(self) -> bool:
        return self.send_key(Key.MENU)

    def netflix(self) -> bool:
        return self.send_key(Key.NETFLIX)

    def amazon(self) -> bool:
        return self.send_key(Key.AMAZON)

    def red(self) -> bool:
        return self.send_key(Key.RED)

    def green(self) -> bool:
        return self.send_key(Key.GREEN)

    def yellow(self) -> bool:
        return self.send_key(Key.YELLOW)

    def blue(self) -> bool:
        return self.send_key(Key.BLUE)


# CLI for testing
if __name__ == "__main__":
    import sys

    tv = SamsungTV("192.168.178.103", mac="80:47:86:E9:B2:17")

    if len(sys.argv) < 2:
        print("Samsung TV Remote Control Library")
        print("\nUsage: python samsung_tv.py <command>")
        print("\nBasic Commands:")
        print("  info         - Get TV info")
        print("  ping         - Check if TV is reachable")
        print("  pair         - Pair with TV")
        print("  key <KEY>    - Send specific key (e.g., KEY_MUTE)")
        print("\nPower:")
        print("  power        - Toggle power")
        print("  on           - Wake-on-LAN")
        print("  on --close   - Wake and close Smart Hub")
        print("\nVolume (UPnP - direct values):")
        print("  volume       - Get current volume")
        print("  volume <n>   - Set volume to n (0-100)")
        print("  mute         - Toggle mute")
        print("  muted        - Get mute status")
        print("  volup [n]    - Volume up (optional: n steps)")
        print("  voldown [n]  - Volume down")
        print("\nChannels:")
        print("  chup         - Channel up")
        print("  chdown       - Channel down")
        print("  ch <num>     - Go to channel number")
        print("\nApps:")
        print("  app <id>     - Launch app by ID")
        print("  appclose <id>- Close app by ID")
        print("  appstatus <id>- Get app status")
        print("\nNavigation:")
        print("  home         - Smart Hub")
        print("  back         - Return/Back")
        print("  exit         - Exit menu")
        print("  text <str>   - Send text input")
        print("\nMedia:")
        print("  play/pause/stop/rw/ff")
        print("\nAvailable keys:", ", ".join(k.name for k in Key))
        print("Available apps:", ", ".join(a.name for a in App))
        sys.exit(0)

    cmd = sys.argv[1].lower()

    try:
        if cmd == "info":
            info = tv.get_info()
            if info:
                print(f"Name: {info.name}")
                print(f"Model: {info.model_name}")
                print(f"Power: {info.power_state}")
                print(f"IP: {info.ip}")
                print(f"MAC: {info.mac}")
            else:
                print("Could not get TV info")

        elif cmd == "pair":
            print("Pairing with TV... Accept on TV screen!")
            if tv.pair(timeout=60):
                print("Pairing successful!")
            else:
                print("Pairing failed or timed out")

        elif cmd == "key" and len(sys.argv) > 2:
            key = sys.argv[2].upper()
            if not key.startswith("KEY_"):
                key = f"KEY_{key}"
            tv.send_key(key)
            print(f"Sent: {key}")

        elif cmd == "mute":
            tv.mute()
            print("Toggled mute")

        elif cmd == "volup":
            steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            tv.volume_up(steps)
            print(f"Volume up ({steps})")

        elif cmd == "voldown":
            steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            tv.volume_down(steps)
            print(f"Volume down ({steps})")

        elif cmd == "chup":
            tv.channel_up()
            print("Channel up")

        elif cmd == "chdown":
            tv.channel_down()
            print("Channel down")

        elif cmd == "ch" and len(sys.argv) > 2:
            ch = int(sys.argv[2])
            tv.channel(ch)
            print(f"Channel {ch}")

        elif cmd == "power":
            tv.power_off()
            print("Power toggle sent")

        elif cmd == "on":
            close_menu = "--close" in sys.argv
            tv.power_on(close_menu=close_menu)
            if close_menu:
                print("Wake-on-LAN sent (will close menu after boot)")
            else:
                print("Wake-on-LAN sent")

        elif cmd == "ping":
            if tv.ping():
                print("TV is reachable")
            else:
                print("TV is not reachable")

        elif cmd == "volume":
            if len(sys.argv) > 2:
                vol = int(sys.argv[2])
                if tv.set_volume(vol):
                    print(f"Volume set to {vol}")
                else:
                    print("Failed to set volume (UPnP not available?)")
            else:
                vol = tv.get_volume()
                if vol is not None:
                    print(f"Volume: {vol}")
                else:
                    print("Could not get volume (UPnP not available?)")

        elif cmd == "muted":
            muted = tv.get_mute_status()
            if muted is not None:
                print(f"Muted: {muted}")
            else:
                print("Could not get mute status")

        elif cmd == "app" and len(sys.argv) > 2:
            app_id = sys.argv[2]
            if tv.run_app(app_id):
                print(f"Launched app: {app_id}")
            else:
                print(f"Failed to launch app: {app_id}")

        elif cmd == "appclose" and len(sys.argv) > 2:
            app_id = sys.argv[2]
            if tv.close_app(app_id):
                print(f"Closed app: {app_id}")
            else:
                print(f"Failed to close app: {app_id}")

        elif cmd == "appstatus" and len(sys.argv) > 2:
            app_id = sys.argv[2]
            status = tv.get_app_status(app_id)
            if status:
                print(f"App status: {json.dumps(status, indent=2)}")
            else:
                print(f"Could not get app status: {app_id}")

        elif cmd == "text" and len(sys.argv) > 2:
            text = " ".join(sys.argv[2:])
            tv.send_text(text)
            print(f"Sent text: {text}")

        elif cmd == "home":
            tv.home()
            print("Home")

        elif cmd == "back":
            tv.back()
            print("Back")

        elif cmd == "exit":
            tv.exit()
            print("Exit")

        elif cmd == "play":
            tv.play()
            print("Play")

        elif cmd == "pause":
            tv.pause()
            print("Pause")

        elif cmd == "stop":
            tv.stop()
            print("Stop")

        elif cmd == "rw":
            tv.rewind()
            print("Rewind")

        elif cmd == "ff":
            tv.fast_forward()
            print("Fast forward")

        elif cmd == "netflix":
            tv.netflix()
            print("Netflix")

        elif cmd == "amazon":
            tv.amazon()
            print("Amazon")

        else:
            # Try as a key name
            try:
                key = Key[cmd.upper()]
                tv.send_key(key)
                print(f"Sent: {key.value}")
            except KeyError:
                print(f"Unknown command: {cmd}")
                sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
