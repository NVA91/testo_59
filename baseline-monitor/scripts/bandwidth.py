#!/usr/bin/env python3
"""
bandwidth.py – Bandbreiten-Test via iperf3 für das Netzwerk-Baseline-Monitoring.

Ablauf:
  1. Konfiguration aus baseline-monitor.conf lesen
  2. Optional: iperf3-Server auf Gegenstelle via SSH starten
  3. iperf3-Client: TCP Upload- und Download-Messung
  4. Ergebnis als JSON in LOG_DIR speichern

Verwendung:
  python3 bandwidth.py --config /pfad/zu/baseline-monitor.conf

Voraussetzung für Loopback-Test (ein Rechner):
  Starte manuell in einem anderen Terminal: iperf3 -s
"""

import argparse
import json
import subprocess
import sys
import time
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


def start_remote_iperf3_server(ssh_user: str, server_ip: str, ssh_key_path: str) -> bool:
    """Startet iperf3-Server auf dem Remote-Host via SSH (ohne Passwort-Abfrage)."""
    cmd = [
        'ssh',
        '-i', ssh_key_path,
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=10',
        f'{ssh_user}@{server_ip}',
        'nohup iperf3 -s -D --logfile /tmp/iperf3-baseline.log 2>/dev/null',
    ]
    print(f'    SSH-Verbindung zu {ssh_user}@{server_ip}...')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if result.returncode == 0:
            print('    iperf3-Server auf Gegenstelle gestartet.')
            time.sleep(2)
            return True
        print(f'    SSH-Fehler (Exit {result.returncode}): {result.stderr.strip()}')
        return False
    except subprocess.TimeoutExpired:
        print('    SSH-Verbindung Timeout.')
        return False
    except FileNotFoundError:
        print('    ssh nicht gefunden.')
        return False


def run_iperf3(server_ip: str, port: int, duration: int, reverse: bool) -> dict:
    """Führt einen iperf3-Lauf aus und gibt das geparste JSON-Ergebnis zurück."""
    direction = 'Download (reverse)' if reverse else 'Upload'
    cmd = ['iperf3', '-c', server_ip, '-p', str(port), '-t', str(duration), '-J']
    if reverse:
        cmd.append('-R')

    print(f'    iperf3 {direction} ({duration}s) ...')
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration + 30,
        )
        if result.stdout:
            try:
                data = json.loads(result.stdout)
                if result.returncode != 0:
                    data['_exit_error'] = result.stderr.strip()
                return data
            except json.JSONDecodeError:
                return {'error': 'JSON-Parsing fehlgeschlagen', 'raw': result.stdout}
        return {'error': result.stderr.strip() or 'Keine Ausgabe'}
    except subprocess.TimeoutExpired:
        return {'error': f'timeout (>{duration + 30}s)'}
    except FileNotFoundError:
        return {'error': 'iperf3 nicht gefunden – installiere: apt install iperf3'}


def extract_mbps(iperf_data: dict, reverse: bool) -> float | None:
    """Extrahiert Bandbreite in Mbit/s aus iperf3-JSON-Ausgabe."""
    try:
        if reverse:
            bps = iperf_data['end']['sum_received']['bits_per_second']
        else:
            bps = iperf_data['end']['sum_sent']['bits_per_second']
        return round(bps / 1e6, 2)
    except (KeyError, TypeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Bandbreiten-Test für Baseline-Monitoring'
    )
    parser.add_argument(
        '--config', required=True,
        help='Pfad zur baseline-monitor.conf'
    )
    args = parser.parse_args()

    config = load_config(args.config)
    log_dir = Path(config.get('LOG_DIR', '/var/log/baseline-monitor'))
    log_dir.mkdir(parents=True, exist_ok=True)

    server_ip = config.get('IPERF3_SERVER_IP', '127.0.0.1')
    port = int(config.get('IPERF3_PORT', '5201'))
    duration = int(config.get('IPERF3_DURATION', '10'))
    ssh_enabled = config.get('SSH_ENABLED', 'false').lower() == 'true'
    ssh_user = config.get('SSH_USER', '')
    ssh_key_path = config.get('SSH_KEY_PATH', '')

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'bandwidth_{timestamp_str}.json'

    print(f"\n{'='*60}")
    print(f"  Bandbreiten-Test  –  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Server    : {server_ip}:{port}")
    print(f"  Dauer     : {duration}s pro Richtung")
    print(f"  SSH-Auto  : {'aktiv' if ssh_enabled else 'deaktiviert'}")
    print(f"{'='*60}")

    ssh_started = False
    if ssh_enabled and server_ip not in ('127.0.0.1', 'localhost'):
        print('\n[0/2] Remote iperf3-Server starten (SSH)...')
        ssh_started = start_remote_iperf3_server(ssh_user, server_ip, ssh_key_path)

    print('\n[1/2] TCP Upload-Test...')
    upload_data = run_iperf3(server_ip, port, duration, reverse=False)
    ul_mbps = extract_mbps(upload_data, reverse=False)

    print('\n[2/2] TCP Download-Test (reverse)...')
    download_data = run_iperf3(server_ip, port, duration, reverse=True)
    dl_mbps = extract_mbps(download_data, reverse=True)

    print('\n  Ergebnis:')
    if ul_mbps is not None:
        print(f'    Upload  : {ul_mbps} Mbit/s')
    else:
        print(f"    Upload  : FEHLER – {upload_data.get('error', 'unbekannt')}")
    if dl_mbps is not None:
        print(f'    Download: {dl_mbps} Mbit/s')
    else:
        print(f"    Download: FEHLER – {download_data.get('error', 'unbekannt')}")

    report = {
        'timestamp': datetime.now().isoformat(),
        'server_ip': server_ip,
        'port': port,
        'duration_s': duration,
        'ssh_enabled': ssh_enabled,
        'ssh_server_started': ssh_started,
        'upload_mbps': ul_mbps,
        'download_mbps': dl_mbps,
        'iperf3_upload': upload_data,
        'iperf3_download': download_data,
    }
    log_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f'\n  Log gespeichert: {log_file}')
    print(f"{'='*60}\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
