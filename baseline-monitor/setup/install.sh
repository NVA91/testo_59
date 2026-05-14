#!/bin/bash
# install.sh – Installiert alle Abhängigkeiten für das Netzwerk-Baseline-Monitoring
#
# Unterstützte Systeme: Ubuntu 24.04 LTS
# Ausführen mit:  sudo bash baseline-monitor/setup/install.sh
#
# Was dieses Skript tut:
#   1. System-Netzwerktools installieren (nmap, arp-scan, mtr-tiny, iperf3, vnstat, curl)
#   2. Python-Bibliotheken für die Auswertung installieren
#   3. Log-Verzeichnis anlegen (/var/log/baseline-monitor)
#   4. Skripte nach /opt/baseline-monitor kopieren
#   5. Systemd-Dateien installieren (Timer bleibt INAKTIV bis zur manuellen Freigabe)

set -euo pipefail

# ---- Root-Prüfung ----
if [ "$(id -u)" -ne 0 ]; then
    echo "FEHLER: Root-Rechte erforderlich."
    echo "Verwendung: sudo bash baseline-monitor/setup/install.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "${SCRIPT_DIR}")"

echo ""
echo "============================================================"
echo "  Netzwerk-Baseline-Monitoring – Installation"
echo "  Ubuntu 24.04 LTS"
echo "============================================================"
echo ""

# ---- 1. System-Pakete ----
echo "[1/5] System-Paketliste aktualisieren..."
apt-get update -qq

echo "[2/5] Netzwerk-Tools installieren..."
apt-get install -y \
    nmap \
    arp-scan \
    mtr-tiny \
    iperf3 \
    vnstat \
    curl
echo "      OK: nmap  arp-scan  mtr-tiny  iperf3  vnstat  curl"

# ---- 2. Python-Pakete ----
echo "[3/5] Python-Bibliotheken installieren..."
# --break-system-packages ist unter Ubuntu 24.04 für systemweite pip-Installation nötig.
# Alternative: python3 -m venv /opt/baseline-monitor/venv && source .../activate
pip3 install \
    networkx \
    plotly \
    pandas \
    paramiko \
    fabric \
    --break-system-packages \
    --quiet
echo "      OK: networkx  plotly  pandas  paramiko  fabric"

# ---- 3. Log-Verzeichnis ----
echo "[4/5] Log-Verzeichnis anlegen..."
mkdir -p /var/log/baseline-monitor
chmod 755 /var/log/baseline-monitor
echo "      OK: /var/log/baseline-monitor"

# ---- 4. Skripte installieren ----
echo "[5/5] Skripte nach /opt/baseline-monitor installieren..."
mkdir -p /opt/baseline-monitor
# Kopiert den gesamten baseline-monitor-Ordner
cp -r "${BASE_DIR}/." /opt/baseline-monitor/
chmod +x /opt/baseline-monitor/run_all.sh
echo "      OK: /opt/baseline-monitor"

# ---- 5. Systemd-Dateien ----
echo ""
echo "      Systemd-Dateien registrieren..."
cp /opt/baseline-monitor/systemd/baseline-monitor.service /etc/systemd/system/
cp /opt/baseline-monitor/systemd/baseline-monitor.timer   /etc/systemd/system/
systemctl daemon-reload
echo "      OK: Systemd-Dateien installiert"
echo "      HINWEIS: Timer ist noch NICHT aktiv (erst nach manuellem Test aktivieren!)"

# ---- Abschluss-Ausgabe ----
echo ""
echo "============================================================"
echo "  Installation erfolgreich abgeschlossen!"
echo ""
echo "  NÄCHSTE SCHRITTE (Sicherheits-Workflow):"
echo ""
echo "  1. Konfiguration an dein Heimnetzwerk anpassen:"
echo "     nano /opt/baseline-monitor/config/baseline-monitor.conf"
echo "     (LATENCY_TARGETS, SCAN_NETWORK, SCAN_INTERFACE, IPERF3_SERVER_IP)"
echo ""
echo "  2. Für Loopback-iPerf3-Test zuerst Server starten:"
echo "     iperf3 -s &"
echo ""
echo "  3. Skripte einzeln manuell testen:"
echo ""
echo "     sudo python3 /opt/baseline-monitor/scripts/portscan.py \\"
echo "          --config /opt/baseline-monitor/config/baseline-monitor.conf"
echo ""
echo "     python3 /opt/baseline-monitor/scripts/latency.py \\"
echo "          --config /opt/baseline-monitor/config/baseline-monitor.conf"
echo ""
echo "     python3 /opt/baseline-monitor/scripts/bandwidth.py \\"
echo "          --config /opt/baseline-monitor/config/baseline-monitor.conf"
echo ""
echo "  4. Logs prüfen:"
echo "     ls -lh /var/log/baseline-monitor/"
echo "     cat /var/log/baseline-monitor/latency_<TIMESTAMP>.json | python3 -m json.tool"
echo ""
echo "  5. Wenn alles plausibel ist – Timer scharf schalten:"
echo "     sudo systemctl enable --now baseline-monitor.timer"
echo "     sudo systemctl list-timers baseline-monitor.timer"
echo ""
echo "  6. Auswertung starten:"
echo "     python3 /opt/baseline-monitor/scripts/analyze.py \\"
echo "          --config /opt/baseline-monitor/config/baseline-monitor.conf \\"
echo "          --html /tmp/baseline-report.html"
echo "============================================================"
echo ""
