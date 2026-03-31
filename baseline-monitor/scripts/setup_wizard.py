#!/usr/bin/env python3
"""
setup_wizard.py – Interaktiver Konfigurations-Wizard für das Baseline-Monitoring.

Führt Schritt für Schritt durch die Einrichtung:
  1. Netzwerk-Interface erkennen und auswählen
  2. Netzwerk-Bereich (CIDR) bestimmen
  3. Latenz-Ziele abfragen und validieren
  4. iPerf3-Server konfigurieren
  5. SSH-Automatisierung (optional)
  6. Ping/MTR/vnstat-Parameter
  7. Zusammenfassung anzeigen und bestätigen
  8. Konfiguration schreiben

Verwendung:
  python3 setup_wizard.py
  python3 setup_wizard.py --config /pfad/zu/baseline-monitor.conf
"""

import argparse
import ipaddress
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ── Farben (ANSI) ──────────────────────────────────────────────

BOLD = '\033[1m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
DIM = '\033[2m'
RESET = '\033[0m'


def cprint(text: str, color: str = '') -> None:
    print(f'{color}{text}{RESET}')


def banner(title: str) -> None:
    width = 60
    print()
    cprint('=' * width, CYAN)
    cprint(f'  {title}', BOLD)
    cprint('=' * width, CYAN)


def step_header(num: int, total: int, title: str) -> None:
    print()
    cprint(f'  Schritt {num}/{total}: {title}', BOLD + CYAN)
    cprint('  ' + '-' * 50, DIM)


# ── Validierung ────────────────────────────────────────────────

def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_valid_cidr(cidr: str) -> bool:
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError:
        return False


def is_valid_hostname(name: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$', name))


def is_valid_target(target: str) -> bool:
    return is_valid_ip(target) or is_valid_hostname(target)


def is_valid_port(port_str: str) -> bool:
    try:
        p = int(port_str)
        return 1 <= p <= 65535
    except ValueError:
        return False


# ── System-Erkennung ──────────────────────────────────────────

def detect_interfaces() -> list:
    """Erkennt verfügbare Netzwerk-Interfaces mit IP-Adressen."""
    interfaces = []
    try:
        result = subprocess.run(
            ['ip', '-o', '-4', 'addr', 'show'],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                idx = parts[0]
                iface = parts[1]
                # IP/CIDR extrahieren
                for i, p in enumerate(parts):
                    if p == 'inet' and i + 1 < len(parts):
                        ip_cidr = parts[i + 1]
                        ip = ip_cidr.split('/')[0]
                        if iface != 'lo':
                            interfaces.append({
                                'name': iface,
                                'ip': ip,
                                'cidr': ip_cidr,
                            })
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return interfaces


def detect_default_gateway() -> str | None:
    """Erkennt das Standard-Gateway."""
    try:
        result = subprocess.run(
            ['ip', 'route', 'show', 'default'],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if 'via' in parts:
                idx = parts.index('via')
                if idx + 1 < len(parts):
                    return parts[idx + 1]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def check_tool_installed(tool: str) -> bool:
    return shutil.which(tool) is not None


def derive_network_cidr(ip_cidr: str) -> str:
    """Leitet Netzwerk-CIDR aus Interface-IP ab (z.B. 192.168.1.5/24 -> 192.168.1.0/24)."""
    try:
        net = ipaddress.ip_network(ip_cidr, strict=False)
        return str(net)
    except ValueError:
        return '192.168.1.0/24'


# ── Eingabe-Helfer ────────────────────────────────────────────

def ask(prompt: str, default: str = '', validator=None, error_msg: str = '') -> str:
    """Fragt den Benutzer nach Eingabe mit optionaler Validierung."""
    while True:
        if default:
            raw = input(f'    {prompt} [{default}]: ').strip()
            value = raw if raw else default
        else:
            value = input(f'    {prompt}: ').strip()

        if validator and not validator(value):
            cprint(f'    {error_msg or "Ungültige Eingabe."}', RED)
            continue
        return value


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Ja/Nein-Frage."""
    suffix = '[J/n]' if default else '[j/N]'
    while True:
        raw = input(f'    {prompt} {suffix}: ').strip().lower()
        if not raw:
            return default
        if raw in ('j', 'ja', 'y', 'yes'):
            return True
        if raw in ('n', 'nein', 'no'):
            return False
        cprint('    Bitte J oder N eingeben.', RED)


def ask_choice(prompt: str, choices: list, default: int = 0) -> int:
    """Auswahl aus einer Liste."""
    for i, c in enumerate(choices):
        marker = ' *' if i == default else ''
        cprint(f'    [{i + 1}] {c}{marker}', '')
    while True:
        raw = input(f'    {prompt} [Standard: {default + 1}]: ').strip()
        if not raw:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return idx
        except ValueError:
            pass
        cprint(f'    Bitte eine Zahl von 1 bis {len(choices)} eingeben.', RED)


# ── Wizard-Schritte ───────────────────────────────────────────

def wizard_interface(interfaces: list) -> tuple:
    """Schritt 1: Netzwerk-Interface auswählen."""
    step_header(1, 7, 'Netzwerk-Interface')

    if not interfaces:
        cprint('    Keine Interfaces automatisch erkannt.', YELLOW)
        iface = ask('Interface-Name (z.B. eth0, enp3s0, wlan0)', 'eth0')
        return iface, ''

    print('    Erkannte Interfaces:')
    choices = [f'{i["name"]:12s}  IP: {i["ip"]:16s}  ({i["cidr"]})' for i in interfaces]
    idx = ask_choice('Interface wählen', choices, default=0)
    selected = interfaces[idx]
    cprint(f'    -> Gewählt: {selected["name"]} ({selected["ip"]})', GREEN)
    return selected['name'], selected.get('cidr', '')


def wizard_network(default_cidr: str) -> str:
    """Schritt 2: Netzwerk-Bereich bestimmen."""
    step_header(2, 7, 'Netzwerk-Bereich (CIDR)')

    if default_cidr:
        net = derive_network_cidr(default_cidr)
        cprint(f'    Automatisch erkannt: {net}', DIM)
    else:
        net = '192.168.1.0/24'

    return ask(
        'Netzwerk-Bereich für Host-Scan', net,
        validator=is_valid_cidr,
        error_msg='Ungültiges CIDR-Format. Beispiel: 192.168.1.0/24',
    )


def wizard_latency_targets(gateway: str | None) -> str:
    """Schritt 3: Latenz-Ziele konfigurieren."""
    step_header(3, 7, 'Latenz-Ziele (Ping / MTR)')

    targets = []

    # Gateway vorschlagen
    if gateway:
        cprint(f'    Gateway erkannt: {gateway}', DIM)
        if ask_yes_no(f'Gateway {gateway} als Ziel hinzufügen?', True):
            targets.append(gateway)

    # Google DNS
    if ask_yes_no('Google DNS (8.8.8.8) hinzufügen?', True):
        targets.append('8.8.8.8')

    # Cloudflare DNS
    if ask_yes_no('Cloudflare DNS (1.1.1.1) hinzufügen?', True):
        targets.append('1.1.1.1')

    # Eigene Ziele
    while True:
        extra = ask(
            'Weiteres Ziel hinzufügen (IP/Hostname, leer=fertig)', '',
        )
        if not extra:
            break
        if is_valid_target(extra):
            targets.append(extra)
            cprint(f'    + {extra} hinzugefügt.', GREEN)
        else:
            cprint(f'    "{extra}" ist keine gültige IP oder Hostname.', RED)

    if not targets:
        cprint('    Keine Ziele gewählt – verwende Standard: 8.8.8.8', YELLOW)
        targets = ['8.8.8.8']

    cprint(f'    Ziele: {", ".join(targets)}', GREEN)
    return ','.join(targets)


def wizard_iperf3() -> dict:
    """Schritt 4: iPerf3 konfigurieren."""
    step_header(4, 7, 'Bandbreiten-Test (iPerf3)')

    print('    iPerf3 benötigt einen Server als Gegenstelle.')
    print('    Optionen:')
    choices = [
        'Loopback (127.0.0.1) – testet nur lokale Performance',
        'Anderer Rechner im Netzwerk – echter Netzwerktest',
        'iPerf3-Test überspringen (Server-IP leer lassen)',
    ]
    idx = ask_choice('Modus wählen', choices, default=0)

    if idx == 0:
        server_ip = '127.0.0.1'
        cprint('    Hinweis: Starte vor dem Test "iperf3 -s &" in einem anderen Terminal.', YELLOW)
    elif idx == 1:
        server_ip = ask(
            'IP des iPerf3-Servers', '',
            validator=is_valid_ip,
            error_msg='Ungültige IP-Adresse.',
        )
    else:
        server_ip = '127.0.0.1'
        cprint('    iPerf3-Test wird mit Loopback konfiguriert (kann später angepasst werden).', YELLOW)

    port = ask(
        'iPerf3-Port', '5201',
        validator=is_valid_port,
        error_msg='Port muss zwischen 1 und 65535 liegen.',
    )

    duration = ask(
        'Testdauer pro Richtung (Sekunden)', '10',
        validator=lambda x: x.isdigit() and 1 <= int(x) <= 300,
        error_msg='Bitte eine Zahl zwischen 1 und 300 eingeben.',
    )

    return {'server_ip': server_ip, 'port': port, 'duration': duration}


def wizard_ssh(iperf3_ip: str) -> dict:
    """Schritt 5: SSH-Automatisierung."""
    step_header(5, 7, 'SSH-Automatisierung')

    if iperf3_ip in ('127.0.0.1', 'localhost', ''):
        cprint('    Nicht benötigt (iPerf3 läuft lokal).', DIM)
        return {'enabled': False, 'user': 'your_user', 'key_path': '/root/.ssh/id_ed25519'}

    print(f'    Der iPerf3-Server ({iperf3_ip}) ist remote.')
    print('    SSH-Automatisierung startet den iperf3-Server automatisch.')

    if not ask_yes_no('SSH-Automatisierung aktivieren?', False):
        return {'enabled': False, 'user': 'your_user', 'key_path': '/root/.ssh/id_ed25519'}

    user = ask('SSH-Benutzername auf dem Server', os.environ.get('USER', 'root'))

    # SSH-Schlüssel suchen
    default_key = ''
    for candidate in [
        Path.home() / '.ssh' / 'id_baseline',
        Path.home() / '.ssh' / 'id_ed25519',
        Path.home() / '.ssh' / 'id_rsa',
    ]:
        if candidate.exists():
            default_key = str(candidate)
            break

    key_path = ask(
        'Pfad zum privaten SSH-Schlüssel', default_key or str(Path.home() / '.ssh' / 'id_ed25519'),
        validator=lambda p: Path(p).exists() or ask_yes_no(f'Datei "{p}" existiert nicht. Trotzdem verwenden?', False),
    )

    # Verbindungstest
    if ask_yes_no('SSH-Verbindung jetzt testen?', True):
        cprint(f'    Teste: ssh -i {key_path} {user}@{iperf3_ip} echo ok ...', DIM)
        try:
            result = subprocess.run(
                ['ssh', '-i', key_path, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                 f'{user}@{iperf3_ip}', 'echo', 'ok'],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                cprint('    SSH-Verbindung erfolgreich!', GREEN)
            else:
                cprint(f'    SSH fehlgeschlagen: {result.stderr.strip()}', RED)
                cprint('    Du kannst die Einstellung trotzdem speichern und später beheben.', YELLOW)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            cprint(f'    SSH-Test fehlgeschlagen: {e}', RED)

    return {'enabled': True, 'user': user, 'key_path': key_path}


def wizard_parameters() -> dict:
    """Schritt 6: Feineinstellungen."""
    step_header(6, 7, 'Feineinstellungen')

    if not ask_yes_no('Standard-Parameter anpassen? (Ping, MTR, vnstat, Logging)', False):
        return {
            'ping_count': '10', 'ping_timeout': '5',
            'mtr_enabled': 'true', 'mtr_cycles': '5',
            'vnstat_enabled': 'true',
            'log_dir': '/var/log/baseline-monitor',
            'log_retention': '30',
        }

    print()
    ping_count = ask(
        'Ping: Pakete pro Ziel', '10',
        validator=lambda x: x.isdigit() and 1 <= int(x) <= 100,
        error_msg='Bitte eine Zahl zwischen 1 und 100.',
    )
    ping_timeout = ask(
        'Ping: Timeout pro Paket (Sekunden)', '5',
        validator=lambda x: x.isdigit() and 1 <= int(x) <= 30,
        error_msg='Bitte eine Zahl zwischen 1 und 30.',
    )

    mtr_enabled = ask_yes_no('MTR (Traceroute) aktivieren?', True)
    mtr_cycles = '5'
    if mtr_enabled:
        mtr_cycles = ask(
            'MTR: Zyklen pro Ziel', '5',
            validator=lambda x: x.isdigit() and 1 <= int(x) <= 20,
            error_msg='Bitte eine Zahl zwischen 1 und 20.',
        )

    vnstat_enabled = ask_yes_no('vnstat (Traffic-Monitoring) aktivieren?', True)

    log_dir = ask('Log-Verzeichnis', '/var/log/baseline-monitor')
    log_retention = ask(
        'Log-Aufbewahrung (Tage)', '30',
        validator=lambda x: x.isdigit() and 1 <= int(x) <= 365,
        error_msg='Bitte eine Zahl zwischen 1 und 365.',
    )

    return {
        'ping_count': ping_count, 'ping_timeout': ping_timeout,
        'mtr_enabled': 'true' if mtr_enabled else 'false',
        'mtr_cycles': mtr_cycles,
        'vnstat_enabled': 'true' if vnstat_enabled else 'false',
        'log_dir': log_dir,
        'log_retention': log_retention,
    }


def wizard_review(config_data: dict) -> bool:
    """Schritt 7: Zusammenfassung anzeigen und bestätigen."""
    step_header(7, 7, 'Zusammenfassung')

    entries = [
        ('Interface', config_data['SCAN_INTERFACE']),
        ('Netzwerk', config_data['SCAN_NETWORK']),
        ('Latenz-Ziele', config_data['LATENCY_TARGETS']),
        ('iPerf3-Server', f"{config_data['IPERF3_SERVER_IP']}:{config_data['IPERF3_PORT']}"),
        ('iPerf3-Dauer', f"{config_data['IPERF3_DURATION']}s pro Richtung"),
        ('SSH', 'aktiv' if config_data['SSH_ENABLED'] == 'true' else 'deaktiviert'),
        ('Ping', f"{config_data['PING_COUNT']} Pakete, {config_data['PING_TIMEOUT']}s Timeout"),
        ('MTR', f"{'aktiv' if config_data['MTR_ENABLED'] == 'true' else 'deaktiviert'}"
                f" ({config_data['MTR_CYCLES']} Zyklen)"),
        ('vnstat', 'aktiv' if config_data['VNSTAT_ENABLED'] == 'true' else 'deaktiviert'),
        ('Log-Verzeichnis', config_data['LOG_DIR']),
        ('Log-Aufbewahrung', f"{config_data['LOG_RETENTION_DAYS']} Tage"),
    ]

    max_label = max(len(e[0]) for e in entries)
    for label, value in entries:
        cprint(f'    {label:<{max_label + 2}} {value}', '')

    print()
    return ask_yes_no('Konfiguration so speichern?', True)


# ── Config schreiben ──────────────────────────────────────────

def write_config(config_data: dict, config_path: Path) -> None:
    """Schreibt die Konfigurationsdatei."""
    # Backup erstellen, falls Datei existiert
    if config_path.exists():
        backup = config_path.with_suffix(f'.conf.bak.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        config_path.rename(backup)
        cprint(f'    Backup der alten Konfiguration: {backup}', DIM)

    config_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        '# ============================================================',
        '# baseline-monitor.conf',
        '# Zentrale Konfiguration für das Netzwerk-Baseline-Monitoring',
        f'# Erstellt am {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} via Setup-Wizard',
        '# ============================================================',
        '',
        '# ---- Netzwerk-Ziele ----',
        f'LATENCY_TARGETS="{config_data["LATENCY_TARGETS"]}"',
        f'SCAN_NETWORK="{config_data["SCAN_NETWORK"]}"',
        f'SCAN_INTERFACE="{config_data["SCAN_INTERFACE"]}"',
        '',
        '# ---- iPerf3 Bandbreiten-Test ----',
        f'IPERF3_SERVER_IP="{config_data["IPERF3_SERVER_IP"]}"',
        f'IPERF3_PORT="{config_data["IPERF3_PORT"]}"',
        f'IPERF3_DURATION="{config_data["IPERF3_DURATION"]}"',
        '',
        '# ---- SSH-Automatisierung ----',
        f'SSH_ENABLED="{config_data["SSH_ENABLED"]}"',
        f'SSH_USER="{config_data["SSH_USER"]}"',
        f'SSH_KEY_PATH="{config_data["SSH_KEY_PATH"]}"',
        '',
        '# ---- Ping ----',
        f'PING_COUNT="{config_data["PING_COUNT"]}"',
        f'PING_TIMEOUT="{config_data["PING_TIMEOUT"]}"',
        '',
        '# ---- MTR ----',
        f'MTR_ENABLED="{config_data["MTR_ENABLED"]}"',
        f'MTR_CYCLES="{config_data["MTR_CYCLES"]}"',
        '',
        '# ---- vnstat ----',
        f'VNSTAT_ENABLED="{config_data["VNSTAT_ENABLED"]}"',
        f'VNSTAT_INTERFACE="{config_data["SCAN_INTERFACE"]}"',
        '',
        '# ---- Logging ----',
        f'LOG_DIR="{config_data["LOG_DIR"]}"',
        f'LOG_RETENTION_DAYS="{config_data["LOG_RETENTION_DAYS"]}"',
        '',
        '# ---- Benachrichtigungen ----',
        'NOTIFY_ENABLED="false"',
        'NOTIFY_EMAIL=""',
        'SMTP_HOST="localhost"',
        'SMTP_PORT="25"',
        'SMTP_FROM="baseline-monitor@localhost"',
    ]

    config_path.write_text('\n'.join(lines) + '\n')
    cprint(f'\n    Konfiguration gespeichert: {config_path}', GREEN)


# ── Hauptprogramm ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Interaktiver Setup-Wizard für das Netzwerk-Baseline-Monitoring'
    )
    parser.add_argument(
        '--config',
        default=str(Path(__file__).resolve().parent.parent / 'config' / 'baseline-monitor.conf'),
        help='Zielpfad für baseline-monitor.conf',
    )
    args = parser.parse_args()
    config_path = Path(args.config)

    banner('Netzwerk-Baseline-Monitoring – Setup-Wizard')
    print()
    cprint('  Dieser Wizard führt dich Schritt für Schritt durch die', '')
    cprint('  Konfiguration. Bei jeder Frage wird ein sinnvoller', '')
    cprint('  Standardwert vorgeschlagen (in eckigen Klammern).', '')
    cprint('  Drücke Enter, um den Standard zu übernehmen.', DIM)

    # Tool-Check
    print()
    cprint('  Verfügbarkeit der benötigten Tools:', BOLD)
    tools = ['nmap', 'arp-scan', 'mtr', 'iperf3', 'vnstat', 'curl', 'ping']
    missing = []
    for tool in tools:
        found = check_tool_installed(tool)
        status = f'{GREEN}OK{RESET}' if found else f'{RED}FEHLT{RESET}'
        print(f'    {tool:<12s}  {status}')
        if not found:
            missing.append(tool)
    if missing:
        cprint(f'\n    Fehlende Tools installieren: sudo apt install {" ".join(missing)}', YELLOW)
        if not ask_yes_no('Trotzdem fortfahren?', True):
            return 1

    # System erkennen
    interfaces = detect_interfaces()
    gateway = detect_default_gateway()

    # Schritte durchlaufen
    iface, ip_cidr = wizard_interface(interfaces)
    network = wizard_network(ip_cidr)
    targets = wizard_latency_targets(gateway)
    iperf3 = wizard_iperf3()
    ssh = wizard_ssh(iperf3['server_ip'])
    params = wizard_parameters()

    # Config-Dictionary zusammenbauen
    config_data = {
        'SCAN_INTERFACE': iface,
        'SCAN_NETWORK': network,
        'LATENCY_TARGETS': targets,
        'IPERF3_SERVER_IP': iperf3['server_ip'],
        'IPERF3_PORT': iperf3['port'],
        'IPERF3_DURATION': iperf3['duration'],
        'SSH_ENABLED': 'true' if ssh['enabled'] else 'false',
        'SSH_USER': ssh['user'],
        'SSH_KEY_PATH': ssh['key_path'],
        'PING_COUNT': params['ping_count'],
        'PING_TIMEOUT': params['ping_timeout'],
        'MTR_ENABLED': params['mtr_enabled'],
        'MTR_CYCLES': params['mtr_cycles'],
        'VNSTAT_ENABLED': params['vnstat_enabled'],
        'LOG_DIR': params['log_dir'],
        'LOG_RETENTION_DAYS': params['log_retention'],
    }

    # Zusammenfassung
    if not wizard_review(config_data):
        cprint('\n  Abgebrochen. Keine Änderungen vorgenommen.', YELLOW)
        return 1

    write_config(config_data, config_path)

    # Nächste Schritte
    print()
    cprint('  Nächste Schritte:', BOLD)
    cprint(f'    1. Preflight-Check:  python3 {Path(__file__).parent}/preflight.py --config {config_path}', '')
    cprint(f'    2. Manueller Test:   sudo bash {Path(__file__).parent.parent}/run_all.sh --config {config_path}', '')
    cprint( '    3. Timer aktivieren: sudo systemctl enable --now baseline-monitor.timer', '')
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
