#!/usr/bin/env python3
"""
portscan.py – Host-Entdeckung und Port-Scan für das Netzwerk-Baseline-Monitoring.

Ablauf:
  1. Konfiguration aus baseline-monitor.conf lesen
  2. arp-scan: Aktive Hosts im Netzwerk finden
  3. nmap:     Offene Ports der gefundenen Hosts scannen
  4. Ergebnis als JSON in LOG_DIR speichern

Verwendung:
  sudo python3 portscan.py --config /pfad/zu/baseline-monitor.conf
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def load_config(config_path: str) -> dict:
    config = {}
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                config[key.strip()] = value.strip().strip('"').strip("'")
    return config


def run_arp_scan(network: str, interface: str) -> dict:
    """Führt arp-scan zur Host-Entdeckung aus."""
    cmd = ['arp-scan', '--interface', interface, network]
    print(f"    Befehl: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        hosts = []
        for line in result.stdout.splitlines():
            parts = line.split('\t')
            # Zeilen mit gültiger IP (3 Punkte, kein Header-Text)
            if len(parts) >= 2 and parts[0].count('.') == 3:
                ip = parts[0].strip()
                mac = parts[1].strip() if len(parts) > 1 else ''
                vendor = parts[2].strip() if len(parts) > 2 else ''
                if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    hosts.append({'ip': ip, 'mac': mac, 'vendor': vendor})
        return {
            'command': ' '.join(cmd),
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'hosts': hosts,
        }
    except subprocess.TimeoutExpired:
        return {'command': ' '.join(cmd), 'error': 'timeout', 'hosts': []}
    except FileNotFoundError:
        return {
            'command': ' '.join(cmd),
            'error': 'arp-scan nicht gefunden – installiere: apt install arp-scan',
            'hosts': [],
        }


def run_nmap(hosts: list) -> dict:
    """Führt nmap-Port-Scan auf den entdeckten Hosts durch."""
    if not hosts:
        return {'skipped': True, 'reason': 'Keine Hosts zum Scannen', 'results': []}

    target_ips = [h['ip'] for h in hosts]
    # -sV: Dienst-Versionen erkennen | --top-ports 100: häufigste 100 Ports
    # -T4: schneller Scan | --open: nur offene Ports ausgeben | -oX -: XML nach stdout
    cmd = ['nmap', '-sV', '--top-ports', '100', '-T4', '--open', '-oX', '-'] + target_ips
    print(f"    Befehl: nmap -sV --top-ports 100 -T4 --open {' '.join(target_ips)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            'command': ' '.join(cmd),
            'returncode': result.returncode,
            'xml_output': result.stdout,
            'stderr': result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {'command': ' '.join(cmd), 'error': 'timeout (>5 min)'}
    except FileNotFoundError:
        return {
            'command': ' '.join(cmd),
            'error': 'nmap nicht gefunden – installiere: apt install nmap',
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Netzwerk-Portscan für Baseline-Monitoring'
    )
    parser.add_argument(
        '--config', required=True,
        help='Pfad zur baseline-monitor.conf'
    )
    args = parser.parse_args()

    config = load_config(args.config)
    log_dir = Path(config.get('LOG_DIR', '/var/log/baseline-monitor'))
    log_dir.mkdir(parents=True, exist_ok=True)

    network = config.get('SCAN_NETWORK', '192.168.1.0/24')
    interface = config.get('SCAN_INTERFACE', 'eth0')
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'portscan_{timestamp_str}.json'

    print(f"\n{'='*60}")
    print(f"  Portscan  –  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Netzwerk  : {network}")
    print(f"  Interface : {interface}")
    print(f"{'='*60}")

    print('\n[1/2] Host-Entdeckung (arp-scan)...')
    arp_result = run_arp_scan(network, interface)
    discovered = arp_result.get('hosts', [])
    print(f'       {len(discovered)} Host(s) gefunden:')
    for h in discovered:
        print(f"       -> {h['ip']:<16}  {h['mac']:<18}  {h.get('vendor', '')}")

    print('\n[2/2] Port-Scan (nmap)...')
    nmap_result = run_nmap(discovered)
    if nmap_result.get('error'):
        print(f"       FEHLER: {nmap_result['error']}")
    elif nmap_result.get('skipped'):
        print(f"       Übersprungen: {nmap_result['reason']}")
    else:
        print(f"       nmap abgeschlossen (Exit-Code: {nmap_result.get('returncode')})")

    report = {
        'timestamp': datetime.now().isoformat(),
        'network': network,
        'interface': interface,
        'arp_scan': arp_result,
        'nmap': nmap_result,
    }
    log_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f'\n  Log gespeichert: {log_file}')
    print(f"{'='*60}\n")

    return 1 if arp_result.get('error') else 0


if __name__ == '__main__':
    sys.exit(main())
