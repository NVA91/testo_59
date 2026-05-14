# Netzwerk-Baseline-Monitoring

Automatisiertes Monitoring für Heimnetzwerke auf Ubuntu 24.04 LTS.
Misst regelmäßig Latenz, Bandbreite und aktive Hosts – alle Ergebnisse
werden als JSON in `/var/log/baseline-monitor/` gespeichert.

## Verzeichnisstruktur

```
baseline-monitor/
├── config/
│   └── baseline-monitor.conf     # Zentrale Konfiguration (hier anpassen!)
├── scripts/
│   ├── setup_wizard.py           # Interaktiver Konfigurations-Wizard
│   ├── preflight.py              # Sicherheits- und Plausibilitätsprüfung
│   ├── portscan.py               # Host-Entdeckung (arp-scan) + Port-Scan (nmap)
│   ├── latency.py                # Latenz-Test (ping + mtr)
│   ├── bandwidth.py              # Bandbreiten-Test (iperf3)
│   └── analyze.py                # Auswertung + HTML-Report (plotly/pandas)
├── systemd/
│   ├── baseline-monitor.service
│   └── baseline-monitor.timer    # Alle 15 Minuten
├── setup/
│   ├── install.sh                # Installations-Skript
│   └── requirements-baseline.txt
└── run_all.sh                    # Master-Skript (Standard + interaktiv)
```

## Voraussetzungen

**System-Pakete:**
```bash
sudo apt install nmap arp-scan mtr-tiny iperf3 vnstat curl
```

**Python-Bibliotheken:**
```bash
pip3 install networkx plotly pandas paramiko fabric --break-system-packages
```

## Installation (Einmalig)

```bash
sudo bash baseline-monitor/setup/install.sh
```

Installiert Abhängigkeiten, kopiert Skripte nach `/opt/baseline-monitor/`
und registriert die Systemd-Dateien. **Der Timer bleibt inaktiv** bis du
ihn nach erfolgreichem manuellem Test freischaltest.

## Konfiguration anpassen

### Option A: Setup-Wizard (empfohlen)

Der interaktive Wizard erkennt das Netzwerk automatisch und führt
Schritt für Schritt durch alle Einstellungen mit Eingabevalidierung:

```bash
python3 /opt/baseline-monitor/scripts/setup_wizard.py
```

Der Wizard:
- Erkennt Netzwerk-Interfaces und Gateway automatisch
- Validiert alle Eingaben (IP-Format, CIDR, Ports, etc.)
- Schlägt sinnvolle Standardwerte vor
- Testet SSH-Verbindung (wenn aktiviert)
- Erstellt automatisch ein Backup der alten Konfiguration

### Option B: Manuell bearbeiten

```bash
nano /opt/baseline-monitor/config/baseline-monitor.conf
```

Zwingend anzupassen:

| Variable | Beschreibung | Beispiel |
|---|---|---|
| `LATENCY_TARGETS` | Ping-Ziele (kommagetrennt) | `192.168.1.1,8.8.8.8` |
| `SCAN_NETWORK` | Netzwerk-Bereich für arp-scan/nmap | `192.168.1.0/24` |
| `SCAN_INTERFACE` | Netzwerk-Interface | `eth0` / `enp3s0` |
| `IPERF3_SERVER_IP` | IP der iperf3-Gegenstelle | `127.0.0.1` für Loopback |

## Preflight-Check (Sicherheitsprüfung)

Nach der Konfiguration prüft der Preflight-Check ob alles bereit ist:

```bash
python3 /opt/baseline-monitor/scripts/preflight.py \
     --config /opt/baseline-monitor/config/baseline-monitor.conf
```

Prüft automatisch:
- Pflicht-Variablen gesetzt und gültig (IP-Format, CIDR, Ports)
- Netzwerk-Interface existiert und hat eine IP
- Alle benötigten Tools installiert (nmap, arp-scan, mtr, iperf3, ...)
- Log-Verzeichnis vorhanden und beschreibbar
- SSH-Schlüssel vorhanden und Rechte korrekt (wenn SSH aktiv)
- Latenz-Ziele erreichbar (Quick-Ping)

Mit `--fix` werden behebbare Probleme automatisch korrigiert:
```bash
sudo python3 scripts/preflight.py --config .../baseline-monitor.conf --fix
```

## Manueller Test (Sicherheits-Workflow)

**Vor der Automatisierung zuerst manuell testen!**

### Interaktiver Modus (empfohlen für den ersten Lauf)

Der interaktive Modus fragt vor **jedem Schritt** nach Bestätigung,
zeigt das Ergebnis und lässt prüfen ob die Ausgabe plausibel ist:

```bash
sudo bash /opt/baseline-monitor/run_all.sh --interactive --preflight
```

Ablauf:
1. Preflight-Check (alle Voraussetzungen prüfen)
2. Portscan → Bestätigung → Ergebnis-Prüfung
3. Latenz-Test → Bestätigung → Ergebnis-Prüfung
4. Bandbreite → Bestätigung → Ergebnis-Prüfung
5. Log-Übersicht → Angebot den Systemd-Timer zu aktivieren

Jeder Schritt kann übersprungen oder abgebrochen werden.

### Einzelne Skripte testen

```bash
# 1. Portscan testen (benötigt Root für arp-scan)
sudo python3 /opt/baseline-monitor/scripts/portscan.py \
     --config /opt/baseline-monitor/config/baseline-monitor.conf

# 2. Latenz testen
python3 /opt/baseline-monitor/scripts/latency.py \
     --config /opt/baseline-monitor/config/baseline-monitor.conf

# 3. Bandbreite testen (für Loopback: vorher "iperf3 -s &" starten)
python3 /opt/baseline-monitor/scripts/bandwidth.py \
     --config /opt/baseline-monitor/config/baseline-monitor.conf

# 4. Logs prüfen
ls -lh /var/log/baseline-monitor/
```

### Automatischer Modus (für Systemd-Timer)

```bash
sudo bash /opt/baseline-monitor/run_all.sh
```

## Automatisierung aktivieren

Wenn alle manuellen Tests erfolgreich waren und die Logs plausibel aussehen:

```bash
sudo systemctl enable --now baseline-monitor.timer
sudo systemctl list-timers baseline-monitor.timer
```

Timer-Status prüfen:
```bash
systemctl status baseline-monitor.timer
journalctl -u baseline-monitor.service -f
```

Timer deaktivieren:
```bash
sudo systemctl disable --now baseline-monitor.timer
```

## SSH-Automatisierung (Optional)

Wenn `IPERF3_SERVER_IP` ein anderer Rechner ist und der iperf3-Server
automatisch gestartet werden soll:

```bash
# SSH-Schlüssel ohne Passphrase erstellen
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_baseline

# Schlüssel auf den Zielrechner kopieren
ssh-copy-id -i ~/.ssh/id_baseline.pub user@192.168.1.50
```

Dann in `baseline-monitor.conf`:
```
SSH_ENABLED="true"
SSH_USER="user"
SSH_KEY_PATH="/root/.ssh/id_baseline"
IPERF3_SERVER_IP="192.168.1.50"
```

## Auswertung & Visualisierung

```bash
# Konsolenausgabe mit Statistiken
python3 /opt/baseline-monitor/scripts/analyze.py \
     --config /opt/baseline-monitor/config/baseline-monitor.conf

# Interaktiven HTML-Report erstellen
python3 /opt/baseline-monitor/scripts/analyze.py \
     --config /opt/baseline-monitor/config/baseline-monitor.conf \
     --html /tmp/baseline-report.html
xdg-open /tmp/baseline-report.html
```

## Log-Format

Alle Skripte schreiben strukturierte JSON-Dateien:

```
/var/log/baseline-monitor/
├── latency_20260331_143000.json
├── bandwidth_20260331_143015.json
├── portscan_20260331_143045.json
└── run_20260331_143000.log
```

Logs werden nach `LOG_RETENTION_DAYS` (Standard: 30 Tage) automatisch gelöscht.
