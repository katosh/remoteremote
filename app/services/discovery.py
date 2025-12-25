"""
TV-Erkennung via SSDP/UPnP - supports Samsung and Philips TVs
"""
import socket
import re
from typing import List, Dict


def discover_all_tvs(timeout: int = 2) -> List[Dict]:
    """
    Discover all supported TVs (Samsung and Philips) on the local network.

    Returns:
        List of found TVs with IP, type, and info
    """
    import concurrent.futures

    discovered = []
    seen_ips = set()

    # Run SSDP discovery for both Samsung and Philips in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        samsung_future = executor.submit(discover_samsung_tvs, timeout)
        philips_future = executor.submit(discover_philips_tvs, timeout)

        # Collect Samsung results
        try:
            samsung_tvs = samsung_future.result(timeout=timeout + 1)
            for tv in samsung_tvs:
                if tv['ip'] not in seen_ips:
                    tv['type'] = 'samsung'
                    discovered.append(tv)
                    seen_ips.add(tv['ip'])
        except Exception:
            pass

        # Collect Philips results
        try:
            philips_tvs = philips_future.result(timeout=timeout + 1)
            for tv in philips_tvs:
                if tv['ip'] not in seen_ips:
                    discovered.append(tv)
                    seen_ips.add(tv['ip'])
        except Exception:
            pass

    return discovered


def discover_philips_tvs(timeout: int = 2) -> List[Dict]:
    """
    Discover Philips Android TVs on the local network via SSDP.

    Returns:
        List of found Philips TVs
    """
    discovered = []

    # SSDP search for Philips TVs
    ssdp_addr = '239.255.255.250'
    ssdp_port = 1900

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
                        'name': 'Philips TV',
                        'source': 'ssdp'
                    }
                    if tv_info['ip'] not in [d['ip'] for d in discovered]:
                        discovered.append(tv_info)

            except socket.timeout:
                break

        sock.close()

    except Exception:
        pass

    return discovered


def discover_samsung_tvs(timeout: int = 3) -> List[Dict]:
    """
    Discover Samsung Smart TVs on the local network via SSDP and HTTP probing.

    Returns:
        List of found TVs with IP and info
    """
    import time
    import urllib.request
    import json

    discovered = []
    seen_ips = set()

    # SSDP Multicast address
    ssdp_addr = '239.255.255.250'
    ssdp_port = 1900

    # Try multiple search targets - Samsung-specific one often doesn't work
    search_targets = [
        'urn:dial-multiscreen-org:service:dial:1',  # Works best for Samsung
        'ssdp:all',
        'urn:samsung.com:device:RemoteControlReceiver:1',
    ]

    for st in search_targets:
        ssdp_request = (
            'M-SEARCH * HTTP/1.1\r\n'
            f'HOST: {ssdp_addr}:{ssdp_port}\r\n'
            'MAN: "ssdp:discover"\r\n'
            f'MX: {timeout}\r\n'
            f'ST: {st}\r\n'
            '\r\n'
        )

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(timeout)

            sock.sendto(ssdp_request.encode(), (ssdp_addr, ssdp_port))

            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(4096)
                    response = data.decode('utf-8', errors='ignore')

                    if 'samsung' in response.lower() and addr[0] not in seen_ips:
                        tv_info = _parse_ssdp_response(response, addr[0])
                        if tv_info:
                            # Try to get detailed info via HTTP
                            details = _get_samsung_details_http(addr[0])
                            if details:
                                tv_info.update(details)
                            discovered.append(tv_info)
                            seen_ips.add(addr[0])

                except socket.timeout:
                    break

            sock.close()

        except Exception:
            pass

        # If we found something, no need to try other search targets
        if discovered:
            break

    return discovered


def _get_samsung_details_http(ip: str, timeout: float = 2.0) -> Dict:
    """Get Samsung TV details via HTTP API (works without pairing)."""
    import urllib.request
    import json

    try:
        req = urllib.request.Request(f'http://{ip}:8001/api/v2/', method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            device = data.get('device', {})
            return {
                'name': data.get('name', 'Samsung TV'),
                'model': device.get('modelName'),
                'mac': device.get('wifiMac'),
                'source': 'http'
            }
    except Exception:
        pass
    return {}


def _parse_ssdp_response(response: str, ip: str) -> Dict:
    """SSDP-Antwort parsen"""
    info = {'ip': ip}

    # Location Header extrahieren
    location_match = re.search(r'LOCATION:\s*(.+)', response, re.IGNORECASE)
    if location_match:
        info['location'] = location_match.group(1).strip()

    # Server Header
    server_match = re.search(r'SERVER:\s*(.+)', response, re.IGNORECASE)
    if server_match:
        info['server'] = server_match.group(1).strip()

    return info


def get_tv_details(ip: str) -> Dict:
    """Detaillierte Informationen von einem TV abrufen"""
    import subprocess
    import json

    try:
        result = subprocess.run(
            ['curl', '-sk', '--connect-timeout', '5',
             f'https://{ip}:8002/api/v2/'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            device = data.get('device', {})
            return {
                'ip': ip,
                'name': data.get('name', 'Unknown'),
                'model': device.get('modelName', 'Unknown'),
                'mac': device.get('wifiMac', 'Unknown'),
                'power_state': device.get('PowerState', 'Unknown')
            }
    except Exception:
        pass

    return {'ip': ip, 'error': 'Nicht erreichbar'}
