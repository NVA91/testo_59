#!/usr/bin/env python3
"""
analyze.py – Auswertung und Visualisierung der Baseline-Monitoring-Logs.

Liest alle JSON-Logs aus LOG_DIR und erstellt:
  - Konsolenausgabe mit Statistik-Zusammenfassung
  - Optionalen interaktiven HTML-Report (benötigt plotly + pandas)

Verwendung:
  python3 analyze.py --config /pfad/zu/baseline-monitor.conf
  python3 analyze.py --config /pfad/zu/baseline-monitor.conf --html /tmp/report.html
"""

import argparse
import json
import sys
from collections import defaultdict
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


def load_latency_logs(log_dir: Path) -> list:
    records = []
    for f in sorted(log_dir.glob('latency_*.json')):
        try:
            data = json.loads(f.read_text())
            ts = data.get('timestamp', '')
            for entry in data.get('results', []):
                target = entry.get('target', '')
                stats = entry.get('ping', {}).get('stats', {})
                records.append({
                    'timestamp': ts,
                    'target': target,
                    'rtt_avg_ms': stats.get('rtt_avg_ms'),
                    'rtt_min_ms': stats.get('rtt_min_ms'),
                    'rtt_max_ms': stats.get('rtt_max_ms'),
                    'packet_loss_pct': stats.get('packet_loss_pct'),
                    'reachable': entry.get('ping', {}).get('reachable', False),
                })
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return records


def load_bandwidth_logs(log_dir: Path) -> list:
    records = []
    for f in sorted(log_dir.glob('bandwidth_*.json')):
        try:
            data = json.loads(f.read_text())
            records.append({
                'timestamp': data.get('timestamp', ''),
                'server_ip': data.get('server_ip', ''),
                'upload_mbps': data.get('upload_mbps'),
                'download_mbps': data.get('download_mbps'),
            })
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return records


def load_portscan_logs(log_dir: Path) -> list:
    records = []
    for f in sorted(log_dir.glob('portscan_*.json')):
        try:
            data = json.loads(f.read_text())
            hosts = data.get('arp_scan', {}).get('hosts', [])
            records.append({
                'timestamp': data.get('timestamp', ''),
                'network': data.get('network', ''),
                'host_count': len(hosts),
                'hosts': [h['ip'] for h in hosts],
            })
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    return records


def print_latency_summary(records: list) -> None:
    if not records:
        print('    Keine Latenz-Logs gefunden.')
        return
    by_target = defaultdict(list)
    for r in records:
        if r.get('rtt_avg_ms') is not None:
            by_target[r['target']].append(r['rtt_avg_ms'])

    unreachable = sum(1 for r in records if not r.get('reachable'))
    print(f'    Messungen : {len(records)}  (davon nicht erreichbar: {unreachable})')
    for target, rtts in sorted(by_target.items()):
        avg = sum(rtts) / len(rtts)
        print(
            f'    {target:<20}  avg={avg:.1f} ms  '
            f'min={min(rtts):.1f} ms  max={max(rtts):.1f} ms  '
            f'n={len(rtts)}'
        )


def print_bandwidth_summary(records: list) -> None:
    if not records:
        print('    Keine Bandbreiten-Logs gefunden.')
        return
    ul = [r['upload_mbps'] for r in records if r.get('upload_mbps') is not None]
    dl = [r['download_mbps'] for r in records if r.get('download_mbps') is not None]
    print(f'    Messungen : {len(records)}')
    if ul:
        print(
            f'    Upload    : avg={sum(ul)/len(ul):.1f}  '
            f'min={min(ul):.1f}  max={max(ul):.1f} Mbit/s'
        )
    if dl:
        print(
            f'    Download  : avg={sum(dl)/len(dl):.1f}  '
            f'min={min(dl):.1f}  max={max(dl):.1f} Mbit/s'
        )


def generate_html_report(
    latency_records: list,
    bandwidth_records: list,
    portscan_records: list,
    output_path: Path,
) -> bool:
    """Erstellt einen interaktiven HTML-Report mit plotly."""
    try:
        import pandas as pd
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print(
            '  plotly/pandas nicht installiert.\n'
            '  Installiere: pip3 install plotly pandas --break-system-packages'
        )
        return False

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            'Latenz (RTT avg) über Zeit',
            'Paketverlust über Zeit',
            'Bandbreite (Mbit/s) über Zeit',
            'Hosts im Netzwerk über Zeit',
        ],
    )

    if latency_records:
        df = pd.DataFrame(latency_records)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        for target in df['target'].unique():
            t = df[df['target'] == target]
            rtt = t.dropna(subset=['rtt_avg_ms'])
            if not rtt.empty:
                fig.add_trace(
                    go.Scatter(
                        x=rtt['timestamp'], y=rtt['rtt_avg_ms'],
                        mode='lines+markers', name=f'RTT {target}',
                    ),
                    row=1, col=1,
                )
            loss = t.dropna(subset=['packet_loss_pct'])
            if not loss.empty:
                fig.add_trace(
                    go.Scatter(
                        x=loss['timestamp'], y=loss['packet_loss_pct'],
                        mode='lines+markers', name=f'Loss {target}',
                    ),
                    row=1, col=2,
                )

    if bandwidth_records:
        df = pd.DataFrame(bandwidth_records)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        ul = df.dropna(subset=['upload_mbps'])
        if not ul.empty:
            fig.add_trace(
                go.Scatter(
                    x=ul['timestamp'], y=ul['upload_mbps'],
                    mode='lines+markers', name='Upload',
                ),
                row=2, col=1,
            )
        dl = df.dropna(subset=['download_mbps'])
        if not dl.empty:
            fig.add_trace(
                go.Scatter(
                    x=dl['timestamp'], y=dl['download_mbps'],
                    mode='lines+markers', name='Download',
                ),
                row=2, col=1,
            )

    if portscan_records:
        df = pd.DataFrame(portscan_records)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        fig.add_trace(
            go.Scatter(
                x=df['timestamp'], y=df['host_count'],
                mode='lines+markers', name='Hosts',
            ),
            row=2, col=2,
        )

    fig.update_layout(
        title=(
            f'Netzwerk-Baseline-Monitoring – Report '
            f'{datetime.now().strftime("%Y-%m-%d %H:%M")}'
        ),
        height=800,
        template='plotly_dark',
    )
    fig.write_html(str(output_path))
    print(f'  HTML-Report gespeichert: {output_path}')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Analysiert Baseline-Monitoring-Logs und erstellt Berichte'
    )
    parser.add_argument('--config', required=True, help='Pfad zur baseline-monitor.conf')
    parser.add_argument('--html', default=None, help='Pfad für HTML-Report (optional)')
    args = parser.parse_args()

    config = load_config(args.config)
    log_dir = Path(config.get('LOG_DIR', '/var/log/baseline-monitor'))

    print(f"\n{'='*60}")
    print(f"  Baseline-Analyse  –  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Log-Verzeichnis  : {log_dir}")
    print(f"{'='*60}")

    if not log_dir.exists():
        print(f'\n  FEHLER: Log-Verzeichnis nicht gefunden: {log_dir}')
        print('  Zuerst einen Monitoring-Lauf starten: sudo bash run_all.sh')
        return 1

    latency_records = load_latency_logs(log_dir)
    bandwidth_records = load_bandwidth_logs(log_dir)
    portscan_records = load_portscan_logs(log_dir)

    latency_files = list(log_dir.glob('latency_*.json'))
    bandwidth_files = list(log_dir.glob('bandwidth_*.json'))
    portscan_files = list(log_dir.glob('portscan_*.json'))

    print(f'\n  Gefundene Log-Dateien:')
    print(f'    Latenz    : {len(latency_files)}')
    print(f'    Bandbreite: {len(bandwidth_files)}')
    print(f'    Portscan  : {len(portscan_files)}')

    print('\n  --- Latenz ---')
    print_latency_summary(latency_records)

    print('\n  --- Bandbreite ---')
    print_bandwidth_summary(bandwidth_records)

    if portscan_records:
        latest = portscan_records[-1]
        ts = latest['timestamp'][:19].replace('T', ' ')
        print(f'\n  --- Letzter Portscan ({ts}) ---')
        print(f"    Netzwerk : {latest['network']}")
        print(f"    Hosts    : {latest['host_count']}  –  {', '.join(latest['hosts'])}")

    if args.html:
        print('\n  --- HTML-Report ---')
        generate_html_report(
            latency_records, bandwidth_records, portscan_records,
            Path(args.html),
        )

    print(f"\n{'='*60}\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
