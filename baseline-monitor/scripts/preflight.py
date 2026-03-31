#!/usr/bin/env python3
"""
preflight.py – Sicherheits- und Plausibilitätsprüfung vor dem Monitoring-Lauf.

Prüft:
  1. Konfigurationsdatei vorhanden und lesbar
  2. Alle Pflicht-Variablen gesetzt und gültig
  3. Netzwerk-Interface existiert und hat eine IP
  4. Benötigte System-Tools installiert
  5. Log-Verzeichnis beschreibbar
  6. SSH-Schlüssel vorhanden (wenn SSH aktiviert)
  7. iPerf3-Server erreichbar (optional)
  8. Latenz-Ziele erreichbar (Quick-Ping)

Verwendung:
  python3 preflight.py --config /pfad/zu/baseline-monitor.conf
  python3 preflight.py --config /pfad/zu/baseline-monitor.conf --fix

Exit-Codes:
  0 = Alle Prüfungen bestanden
  1 = Mindestens eine kritische Prüfung fehlgeschlagen
  2 = Warnungen, aber grundsätzlich lauffähig
"""

import argparse
import ipaddress
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ── Farben ─────────────────────────────────────────────────────

BOLD = '\033[1m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
DIM = '\033[2m'
RESET = '\033[0m'

OK = f'  [{GREEN}OK{RESET}]    '
WARN = f'  [{YELLOW}WARNUNG{RESET}] '
FAIL = f'  [{RED}FEHLER{RESET}]  '
INFO = f'  [{DIM}INFO{RESET}]    '


# ── Config laden ──────────────────────────────────────────────

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


# ── Validierung ───────────────────────────────────────────────

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


# ── Prüfungen ─────────────────────────────────────────────────

class PreflightChecker:
    """Sammelt Prüfergebnisse und gibt eine Zusammenfassung aus."""

    def __init__(self, config: dict, config_path: str, auto_fix: bool = False):
        self.config = config
        self.config_path = config_path
        self.auto_fix = auto_fix
        self.errors = 0
        self.warnings = 0

    def ok(self, msg: str) -> None:
        print(f'{OK}{msg}')

    def warn(self, msg: str) -> None:
        print(f'{WARN}{msg}')
        self.warnings += 1

    def fail(self, msg: str) -> None:
        print(f'{FAIL}{msg}')
        self.errors += 1

    def info(self, msg: str) -> None:
        print(f'{INFO}{msg}')

    # ── Einzelne Checks ───────────────────────────────────────

    def check_required_vars(self) -> None:
        """Prüft ob alle Pflicht-Variablen gesetzt sind."""
        required = [
            'LATENCY_TARGETS', 'SCAN_NETWORK', 'SCAN_INTERFACE',
            'IPERF3_SERVER_IP', 'LOG_DIR',
        ]
        for var in required:
            value = self.config.get(var, '')
            if not value:
                self.fail(f'Pflicht-Variable {var} ist leer oder fehlt.')
            else:
                self.ok(f'{var} = {value}')

    def check_cidr_format(self) -> None:
        """Prüft SCAN_NETWORK auf gültiges CIDR-Format."""
        cidr = self.config.get('SCAN_NETWORK', '')
        if cidr and is_valid_cidr(cidr):
            self.ok(f'SCAN_NETWORK "{cidr}" ist ein gültiges CIDR.')
        elif cidr:
            self.fail(f'SCAN_NETWORK "{cidr}" ist kein gültiges CIDR (z.B. 192.168.1.0/24).')
        # Wenn leer, wird in check_required_vars gemeldet

    def check_ip_formats(self) -> None:
        """Prüft IP-Adressen auf gültiges Format."""
        # Latenz-Ziele
        targets = self.config.get('LATENCY_TARGETS', '')
        for t in targets.split(','):
            t = t.strip()
            if not t:
                continue
            if is_valid_ip(t):
                self.ok(f'Latenz-Ziel {t} ist eine gültige IP.')
            elif re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.\-]+$', t):
                self.ok(f'Latenz-Ziel {t} sieht wie ein gültiger Hostname aus.')
            else:
                self.warn(f'Latenz-Ziel "{t}" ist weder IP noch gültiger Hostname.')

        # iPerf3-Server
        server = self.config.get('IPERF3_SERVER_IP', '')
        if server and is_valid_ip(server):
            self.ok(f'IPERF3_SERVER_IP "{server}" ist eine gültige IP.')
        elif server:
            self.fail(f'IPERF3_SERVER_IP "{server}" ist keine gültige IP.')

    def check_interface(self) -> None:
        """Prüft ob das konfigurierte Interface existiert."""
        iface = self.config.get('SCAN_INTERFACE', '')
        if not iface:
            return

        iface_path = Path(f'/sys/class/net/{iface}')
        if iface_path.exists():
            self.ok(f'Interface "{iface}" existiert.')
            # IP prüfen
            try:
                result = subprocess.run(
                    ['ip', '-4', 'addr', 'show', iface],
                    capture_output=True, text=True, timeout=5,
                )
                if 'inet ' in result.stdout:
                    ip_match = re.search(r'inet (\S+)', result.stdout)
                    if ip_match:
                        self.ok(f'Interface "{iface}" hat IP: {ip_match.group(1)}')
                else:
                    self.warn(f'Interface "{iface}" hat keine IPv4-Adresse.')
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.warn(f'Konnte IP von "{iface}" nicht prüfen.')
        else:
            available = [p.name for p in Path('/sys/class/net').iterdir() if p.name != 'lo']
            self.fail(
                f'Interface "{iface}" existiert nicht. '
                f'Verfügbar: {", ".join(available) or "keine gefunden"}'
            )

    def check_tools(self) -> None:
        """Prüft ob alle benötigten Tools installiert sind."""
        critical = ['nmap', 'arp-scan', 'ping']
        optional = ['mtr', 'iperf3', 'vnstat', 'curl']

        for tool in critical:
            if shutil.which(tool):
                self.ok(f'Tool "{tool}" installiert: {shutil.which(tool)}')
            else:
                self.fail(f'Tool "{tool}" nicht installiert (apt install {tool}).')

        for tool in optional:
            # Prüfe ob Feature aktiviert ist
            skip = False
            if tool == 'mtr' and self.config.get('MTR_ENABLED', 'true').lower() != 'true':
                skip = True
            if tool == 'vnstat' and self.config.get('VNSTAT_ENABLED', 'true').lower() != 'true':
                skip = True

            if shutil.which(tool):
                self.ok(f'Tool "{tool}" installiert.')
            elif skip:
                self.info(f'Tool "{tool}" nicht installiert (Feature deaktiviert – kein Problem).')
            else:
                self.warn(f'Tool "{tool}" nicht installiert (apt install {tool}).')

    def check_log_dir(self) -> None:
        """Prüft Log-Verzeichnis."""
        log_dir = Path(self.config.get('LOG_DIR', '/var/log/baseline-monitor'))

        if log_dir.exists():
            if os.access(str(log_dir), os.W_OK):
                self.ok(f'Log-Verzeichnis "{log_dir}" existiert und ist beschreibbar.')
            else:
                self.fail(f'Log-Verzeichnis "{log_dir}" existiert, aber ist NICHT beschreibbar.')
                if self.auto_fix:
                    self.info('Versuche Verzeichnis-Rechte zu setzen (benötigt Root)...')
                    try:
                        log_dir.chmod(0o755)
                        self.ok('Rechte korrigiert.')
                    except PermissionError:
                        self.fail('Rechte konnten nicht korrigiert werden (sudo nötig).')
        else:
            if self.auto_fix:
                try:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    self.ok(f'Log-Verzeichnis "{log_dir}" wurde angelegt.')
                except PermissionError:
                    self.fail(f'Log-Verzeichnis "{log_dir}" konnte nicht angelegt werden (sudo nötig).')
            else:
                self.warn(
                    f'Log-Verzeichnis "{log_dir}" existiert nicht. '
                    f'Wird beim ersten Lauf angelegt oder: mkdir -p {log_dir}'
                )

    def check_ssh(self) -> None:
        """Prüft SSH-Konfiguration wenn aktiviert."""
        if self.config.get('SSH_ENABLED', 'false').lower() != 'true':
            self.info('SSH-Automatisierung deaktiviert – übersprungen.')
            return

        key_path = Path(self.config.get('SSH_KEY_PATH', ''))
        user = self.config.get('SSH_USER', '')
        server = self.config.get('IPERF3_SERVER_IP', '')

        if not user or user == 'your_user':
            self.fail('SSH_USER ist nicht gesetzt oder noch auf "your_user".')

        if key_path.exists():
            self.ok(f'SSH-Schlüssel existiert: {key_path}')
            # Rechte prüfen
            mode = oct(key_path.stat().st_mode)[-3:]
            if mode in ('600', '400'):
                self.ok(f'SSH-Schlüssel hat sichere Rechte ({mode}).')
            else:
                self.warn(
                    f'SSH-Schlüssel hat Rechte {mode} (sollte 600 sein). '
                    f'Fix: chmod 600 {key_path}'
                )
                if self.auto_fix:
                    key_path.chmod(0o600)
                    self.ok('Rechte auf 600 korrigiert.')
        else:
            self.fail(f'SSH-Schlüssel nicht gefunden: {key_path}')

    def check_numeric_values(self) -> None:
        """Prüft dass numerische Werte gültig sind."""
        checks = [
            ('PING_COUNT', 1, 100),
            ('PING_TIMEOUT', 1, 30),
            ('MTR_CYCLES', 1, 20),
            ('IPERF3_PORT', 1, 65535),
            ('IPERF3_DURATION', 1, 300),
            ('LOG_RETENTION_DAYS', 1, 365),
        ]
        for var, min_val, max_val in checks:
            raw = self.config.get(var, '')
            if not raw:
                continue
            try:
                val = int(raw)
                if min_val <= val <= max_val:
                    self.ok(f'{var} = {val} (gültig: {min_val}–{max_val})')
                else:
                    self.warn(f'{var} = {val} liegt außerhalb {min_val}–{max_val}.')
            except ValueError:
                self.fail(f'{var} = "{raw}" ist keine gültige Zahl.')

    def check_quick_ping(self) -> None:
        """Schneller Erreichbarkeits-Test der ersten Latenz-Ziele."""
        targets = self.config.get('LATENCY_TARGETS', '')
        if not targets:
            return

        first_targets = [t.strip() for t in targets.split(',') if t.strip()][:3]
        for target in first_targets:
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '2', target],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    # RTT extrahieren
                    rtt_match = re.search(r'time=([\d.]+)', result.stdout)
                    rtt = f' ({rtt_match.group(1)} ms)' if rtt_match else ''
                    self.ok(f'Ping {target} erreichbar{rtt}.')
                else:
                    self.warn(f'Ping {target} nicht erreichbar.')
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.warn(f'Ping {target} fehlgeschlagen (Timeout/Tool fehlt).')

    # ── Zusammenfassung ───────────────────────────────────────

    def summary(self) -> int:
        """Gibt Zusammenfassung aus und gibt Exit-Code zurück."""
        print()
        print(f'  {"=" * 50}')
        if self.errors == 0 and self.warnings == 0:
            print(f'  {GREEN}{BOLD}Alle Prüfungen bestanden!{RESET}')
            print(f'  Das System ist bereit für den Monitoring-Lauf.')
            return 0
        elif self.errors == 0:
            print(f'  {YELLOW}{BOLD}{self.warnings} Warnung(en){RESET}, aber grundsätzlich lauffähig.')
            return 2
        else:
            print(f'  {RED}{BOLD}{self.errors} Fehler{RESET}, {self.warnings} Warnung(en).')
            print(f'  Bitte behebe die Fehler bevor du den Monitoring-Lauf startest.')
            print(f'  Tipp: Nutze den Setup-Wizard: python3 scripts/setup_wizard.py')
            return 1


# ── Hauptprogramm ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Preflight-Check für das Netzwerk-Baseline-Monitoring'
    )
    parser.add_argument('--config', required=True, help='Pfad zur baseline-monitor.conf')
    parser.add_argument(
        '--fix', action='store_true',
        help='Versuche erkannte Probleme automatisch zu beheben',
    )
    args = parser.parse_args()

    config_path = Path(args.config)

    print()
    print(f'  {"=" * 50}')
    print(f'  {BOLD}Preflight-Check – Netzwerk-Baseline-Monitoring{RESET}')
    print(f'  Konfiguration: {config_path}')
    print(f'  {"=" * 50}')

    # Config laden
    if not config_path.exists():
        print(f'{FAIL}Konfigurationsdatei nicht gefunden: {config_path}')
        print(f'{INFO}Starte den Setup-Wizard: python3 scripts/setup_wizard.py')
        return 1

    try:
        config = load_config(str(config_path))
    except Exception as e:
        print(f'{FAIL}Konfigurationsdatei konnte nicht gelesen werden: {e}')
        return 1

    print(f'{OK}Konfigurationsdatei geladen ({len(config)} Einträge).')

    checker = PreflightChecker(config, str(config_path), auto_fix=args.fix)

    print(f'\n  {BOLD}--- Pflicht-Variablen ---{RESET}')
    checker.check_required_vars()

    print(f'\n  {BOLD}--- Format-Validierung ---{RESET}')
    checker.check_cidr_format()
    checker.check_ip_formats()
    checker.check_numeric_values()

    print(f'\n  {BOLD}--- System-Umgebung ---{RESET}')
    checker.check_interface()
    checker.check_tools()
    checker.check_log_dir()

    print(f'\n  {BOLD}--- SSH-Konfiguration ---{RESET}')
    checker.check_ssh()

    print(f'\n  {BOLD}--- Erreichbarkeits-Test ---{RESET}')
    checker.check_quick_ping()

    return checker.summary()


if __name__ == '__main__':
    sys.exit(main())
