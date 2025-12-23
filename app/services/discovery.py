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
    Discover Philips Android TVs on the local network.

    Returns:
        List of found Philips TVs
    """
    import concurrent.futures

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

    # Scan common IPs for Philips API in parallel
    ips_to_check = []
    for local_ip in _get_local_ips():
        parts = local_ip.split('.')
        if len(parts) == 4:
            subnet = '.'.join(parts[:3])
            for last_octet in [1, 100, 101, 102, 103, 104, 105]:
                ip = f'{subnet}.{last_octet}'
                if ip not in [d['ip'] for d in discovered]:
                    ips_to_check.append(ip)

    # Check IPs in parallel with short timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        future_to_ip = {executor.submit(_check_philips_api, ip, 0.5): ip for ip in ips_to_check}
        for future in concurrent.futures.as_completed(future_to_ip, timeout=2):
            ip = future_to_ip[future]
            try:
                if future.result():
                    discovered.append({
                        'ip': ip,
                        'type': 'philips',
                        'name': 'Philips TV',
                        'source': 'scan'
                    })
            except Exception:
                pass

    return discovered


def _check_philips_api(ip: str, timeout: float = 0.5) -> bool:
    """Check if Philips TV API responds on given IP"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, 1926))
        sock.close()
        return result == 0
    except Exception:
        return False


def discover_samsung_tvs(timeout: int = 2) -> List[Dict]:
    """
    Samsung Smart TVs im lokalen Netzwerk finden via SSDP.

    Returns:
        Liste von gefundenen TVs mit IP und Informationen
    """
    discovered = []

    # SSDP Multicast-Adresse
    ssdp_addr = '239.255.255.250'
    ssdp_port = 1900

    # SSDP M-SEARCH Request
    ssdp_request = (
        'M-SEARCH * HTTP/1.1\r\n'
        f'HOST: {ssdp_addr}:{ssdp_port}\r\n'
        'MAN: "ssdp:discover"\r\n'
        f'MX: {timeout}\r\n'
        'ST: urn:samsung.com:device:RemoteControlReceiver:1\r\n'
        '\r\n'
    )

    try:
        # UDP Socket erstellen
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        # Request senden
        sock.sendto(ssdp_request.encode(), (ssdp_addr, ssdp_port))

        # Antworten empfangen
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                response = data.decode('utf-8', errors='ignore')

                if 'samsung' in response.lower():
                    tv_info = _parse_ssdp_response(response, addr[0])
                    if tv_info and tv_info not in discovered:
                        discovered.append(tv_info)

            except socket.timeout:
                break

        sock.close()

    except Exception as e:
        pass

    # Zusätzlich: Bekannte IPs direkt prüfen
    discovered.extend(_check_common_ips())

    # Duplikate entfernen
    seen_ips = set()
    unique = []
    for tv in discovered:
        if tv['ip'] not in seen_ips:
            seen_ips.add(tv['ip'])
            unique.append(tv)

    return unique


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


def _get_local_ips() -> List[str]:
    """Get local IP addresses (cross-platform)"""
    local_ips = []

    # Method 1: Use socket to get primary IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        # Connect to a public DNS to determine local IP (doesn't actually send data)
        s.connect(('8.8.8.8', 80))
        local_ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    # Method 2: Try netifaces-style approach via socket
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith('127.') and ip not in local_ips:
                local_ips.append(ip)
    except Exception:
        pass

    return local_ips


def _check_common_ips() -> List[Dict]:
    """Häufige lokale IPs auf Samsung TV API prüfen (parallel)"""
    import concurrent.futures

    found = []

    # Lokales Subnetz ermitteln (cross-platform)
    local_ips = _get_local_ips()

    # Basis-Subnetz extrahieren und IPs sammeln
    ips_to_check = []
    for ip in local_ips:
        parts = ip.split('.')
        if len(parts) == 4:
            subnet = '.'.join(parts[:3])
            for last_octet in [1, 100, 101, 102, 103, 104, 105]:
                ips_to_check.append(f'{subnet}.{last_octet}')

    # Parallel prüfen mit kurzen Timeouts
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        future_to_ip = {executor.submit(_check_samsung_api, ip, 0.5): ip for ip in ips_to_check}
        for future in concurrent.futures.as_completed(future_to_ip, timeout=2):
            ip = future_to_ip[future]
            try:
                if future.result():
                    found.append({'ip': ip, 'source': 'scan'})
            except Exception:
                pass

    return found


def _check_samsung_api(ip: str, timeout: float = 0.5) -> bool:
    """Prüfen ob Samsung TV API auf IP antwortet"""
    # Use socket first for quick port check
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, 8002))
        sock.close()
        return result == 0
    except Exception:
        return False


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
