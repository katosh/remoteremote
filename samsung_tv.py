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
        self._load_token()

    def _load_token(self) -> None:
        """Load token from file if exists"""
        if os.path.exists(self.token_file):
            with open(self.token_file) as f:
                self._token = f.read().strip()

    def _save_token(self, token: str) -> None:
        """Save token to file"""
        self._token = token
        with open(self.token_file, "w") as f:
            f.write(token)

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

    def get_info(self) -> Optional[TVInfo]:
        """Get TV information via REST API"""
        import subprocess
        result = subprocess.run(
            ["curl", "-sk", f"https://{self.ip}:{self.port}/api/v2/"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
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

    # Convenience methods

    def power_off(self) -> bool:
        """Turn TV off"""
        return self.send_key(Key.POWER)

    def power_on(self) -> bool:
        """Turn TV on via Wake-on-LAN"""
        if not self.mac:
            info = self.get_info()
            if not info or not self.mac:
                raise RuntimeError("MAC address not available")

        mac = self.mac.replace(":", "").replace("-", "")
        magic = b'\xff' * 6 + bytes.fromhex(mac) * 16

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, ('255.255.255.255', 9))
        sock.close()
        return True

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
        print("\nCommands:")
        print("  info       - Get TV info")
        print("  pair       - Pair with TV")
        print("  key <KEY>  - Send specific key (e.g., KEY_MUTE)")
        print("  mute       - Toggle mute")
        print("  volup [n]  - Volume up (optional: n steps)")
        print("  voldown [n]- Volume down")
        print("  chup       - Channel up")
        print("  chdown     - Channel down")
        print("  ch <num>   - Go to channel number")
        print("  power      - Toggle power")
        print("  on         - Wake-on-LAN")
        print("  home       - Smart Hub")
        print("  back       - Return/Back")
        print("  exit       - Exit menu")
        print("  play/pause/stop/rw/ff - Media controls")
        print("\nAvailable keys:", ", ".join(k.name for k in Key))
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
            tv.power_on()
            print("Wake-on-LAN sent")

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
