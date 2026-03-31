#!/usr/bin/env python3
"""
latency.py – Latenz-Test via ping und mtr für das Netzwerk-Baseline-Monitoring.

Ablauf:
  1. Konfiguration aus baseline-monitor.conf lesen
  2. ping:  RTT und Paketverlust für jeden Ziel-Host messen
  3. mtr:   Traceroute-Statistik (optional, benötigt mtr-tiny)
  4. Ergebnis als JSON in LOG_DIR speichern

Verwendung:
  python3 latency.py --config /pfad/zu/baseline-monitor.conf
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


def run_ping(target: str, count: int, timeout: int) -> dict:
    """Führt ping aus und parst RTT-Statistiken."""
    cmd = ['ping', '-c', str(count), '-W', str(timeout), target]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=count * (timeout + 1) + 10,
        )
        stats = {}

        rtt_match = re.search(
            r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)',
            result.stdout,
        )
        if rtt_match:
            stats['rtt_min_ms'] = float(rtt_match.group(1))
            stats['rtt_avg_ms'] = float(rtt_match.group(2))
            stats['rtt_max_ms'] = float(rtt_match.group(3))
            stats['rtt_mdev_ms'] = float(rtt_match.group(4))

        loss_match = re.search(r'(\d+)% packet loss', result.stdout)
        if loss_match:
            stats['packet_loss_pct'] = int(loss_match.group(1))

        received_match = re.search(r'(\d+) received', result.stdout)
        if received_match:
            stats['received'] = int(received_match.group(1))

        return {
            'command': ' '.join(cmd),
            'returncode': result.returncode,
            'reachable': result.returncode == 0,
            'stats': stats,
            'raw': result.stdout,
        }
    except subprocess.TimeoutExpired:
        return {
            'command': ' '.join(cmd),
            'error': 'timeout',
            'reachable': False,
            'stats': {},
        }
    except FileNotFoundError:
        return {
            'command': ' '.join(cmd),
            'error': 'ping nicht gefunden',
            'reachable': False,
            'stats': {},
        }


def run_mtr(target: str, cycles: int) -> dict:
    """Führt mtr im Report-Modus aus und gibt JSON-Ausgabe zurück."""
    cmd = ['mtr', '--report', '--report-cycles', str(cycles), '--json', target]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cycles * 3 + 30,
        )
        mtr_data = None
        if result.stdout:
            try:
                mtr_data = json.loads(result.stdout)
            except json.JSONDecodeError:
                mtr_data = {'raw': result.stdout}
        return {
            'command': ' '.join(cmd),
            'returncode': result.returncode,
            'data': mtr_data,
            'stderr': result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {'command': ' '.join(cmd), 'error': 'timeout'}
    except FileNotFoundError:
        return {
            'command': ' '.join(cmd),
            'error': 'mtr nicht gefunden – installiere: apt install mtr-tiny',
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Latenz-Test für Baseline-Monitoring'
    )
    parser.add_argument(
        '--config', required=True,
        help='Pfad zur baseline-monitor.conf'
    )
    args = parser.parse_args()

    config = load_config(args.config)
    log_dir = Path(config.get('LOG_DIR', '/var/log/baseline-monitor'))
    log_dir.mkdir(parents=True, exist_ok=True)

    targets_raw = config.get('LATENCY_TARGETS', '8.8.8.8')
    targets = [t.strip() for t in targets_raw.split(',') if t.strip()]
    ping_count = int(config.get('PING_COUNT', '10'))
    ping_timeout = int(config.get('PING_TIMEOUT', '5'))
    mtr_enabled = config.get('MTR_ENABLED', 'true').lower() == 'true'
    mtr_cycles = int(config.get('MTR_CYCLES', '5'))

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'latency_{timestamp_str}.json'

    print(f"\n{'='*60}")
    print(f"  Latenz-Test  –  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Ziele       : {', '.join(targets)}")
    print(f"  ping        : {ping_count} Pakete, Timeout {ping_timeout}s")
    print(f"  mtr         : {'aktiv (' + str(mtr_cycles) + ' Zyklen)' if mtr_enabled else 'deaktiviert'}")
    print(f"{'='*60}")

    results = []
    for i, target in enumerate(targets, 1):
        print(f'\n[{i}/{len(targets)}] Ziel: {target}')

        print(f'    ping {target} ({ping_count} Pakete)...')
        ping_result = run_ping(target, ping_count, ping_timeout)
        stats = ping_result.get('stats', {})

        if ping_result.get('reachable'):
            print(
                f"    OK  avg={stats.get('rtt_avg_ms', '?')} ms  "
                f"min={stats.get('rtt_min_ms', '?')} ms  "
                f"max={stats.get('rtt_max_ms', '?')} ms  "
                f"loss={stats.get('packet_loss_pct', '?')}%"
            )
        else:
            print(f"    NICHT ERREICHBAR  ({ping_result.get('error', 'keine Antwort')})")

        entry = {'target': target, 'ping': ping_result}

        if mtr_enabled and ping_result.get('reachable'):
            print(f'    mtr {target} ({mtr_cycles} Zyklen)...')
            mtr_result = run_mtr(target, mtr_cycles)
            if mtr_result.get('error'):
                print(f"    mtr FEHLER: {mtr_result['error']}")
            else:
                print('    mtr abgeschlossen.')
            entry['mtr'] = mtr_result

        results.append(entry)

    report = {
        'timestamp': datetime.now().isoformat(),
        'targets': targets,
        'ping_count': ping_count,
        'mtr_enabled': mtr_enabled,
        'mtr_cycles': mtr_cycles,
        'results': results,
    }
    log_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f'\n  Log gespeichert: {log_file}')
    print(f"{'='*60}\n")

    return 0


if __name__ == '__main__':
    sys.exit(main())
