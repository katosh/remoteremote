"""
TV-Erkennung via SSDP/UPnP
"""
import socket
import re
from typing import List, Dict


def discover_samsung_tvs(timeout: int = 5) -> List[Dict]:
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


def _check_common_ips() -> List[Dict]:
    """Häufige lokale IPs auf Samsung TV API prüfen"""
    import subprocess

    found = []

    # Lokales Subnetz ermitteln
    try:
        result = subprocess.run(
            ['hostname', '-I'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            local_ips = result.stdout.strip().split()
        else:
            local_ips = []
    except Exception:
        local_ips = []

    # Basis-Subnetz extrahieren
    subnets = set()
    for ip in local_ips:
        parts = ip.split('.')
        if len(parts) == 4:
            subnets.add('.'.join(parts[:3]))

    # Bekannte TV-IPs im Subnetz prüfen
    for subnet in subnets:
        for last_octet in [1, 100, 101, 102, 103, 104, 105]:
            ip = f'{subnet}.{last_octet}'
            if _check_samsung_api(ip):
                found.append({'ip': ip, 'source': 'scan'})

    return found


def _check_samsung_api(ip: str, timeout: int = 2) -> bool:
    """Prüfen ob Samsung TV API auf IP antwortet"""
    import subprocess

    try:
        result = subprocess.run(
            ['curl', '-sk', '--connect-timeout', str(timeout),
             f'https://{ip}:8002/api/v2/'],
            capture_output=True,
            text=True,
            timeout=timeout + 1
        )
        return 'Samsung' in result.stdout
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
