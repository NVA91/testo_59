#!/bin/bash
# run_all.sh – Führt alle Baseline-Monitoring-Skripte nacheinander aus.
#
# Verwendung:
#   sudo bash run_all.sh
#   sudo bash run_all.sh --config /pfad/zu/baseline-monitor.conf
#
# Wird automatisch vom Systemd-Timer aufgerufen.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config/baseline-monitor.conf"
SCRIPTS_DIR="${SCRIPT_DIR}/scripts"

# Optionales --config Argument
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config) CONFIG_FILE="$2"; shift 2 ;;
        *) echo "Unbekannte Option: $1"; exit 1 ;;
    esac
done

# Konfigurationsdatei prüfen
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "FEHLER: Konfigurationsdatei nicht gefunden: ${CONFIG_FILE}"
    echo "Kopiere und passe an: cp baseline-monitor/config/baseline-monitor.conf /etc/baseline-monitor/"
    exit 1
fi

# LOG_DIR aus Config auslesen
LOG_DIR=$(grep "^LOG_DIR=" "${CONFIG_FILE}" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "/var/log/baseline-monitor")
mkdir -p "${LOG_DIR}"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
RUN_LOG="${LOG_DIR}/run_${TIMESTAMP}.log"

echo ""
echo "============================================================"
echo "  Netzwerk-Baseline-Monitoring"
echo "  Gestartet : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Konfiguration: ${CONFIG_FILE}"
echo "  Ausgabe   : ${RUN_LOG}"
echo "============================================================"

# Funktion: Skript ausführen, Ausgabe auch in Log-Datei schreiben
run_script() {
    local label="$1"
    local script="$2"

    echo ""
    echo "------------------------------------------------------------"
    echo "  ${label}"
    echo "------------------------------------------------------------"

    if python3 "${script}" --config "${CONFIG_FILE}" 2>&1 | tee -a "${RUN_LOG}"; then
        echo "" | tee -a "${RUN_LOG}"
        echo "  [OK] ${label}" | tee -a "${RUN_LOG}"
    else
        EXIT_CODE=$?
        echo "" | tee -a "${RUN_LOG}"
        echo "  [FEHLER] ${label} (Exit-Code: ${EXIT_CODE})" | tee -a "${RUN_LOG}"
        # Nicht abbrechen – restliche Tests sollen trotzdem laufen
    fi
}

run_script "1/3  Portscan       (nmap + arp-scan)" "${SCRIPTS_DIR}/portscan.py"
run_script "2/3  Latenz-Test    (ping + mtr)"       "${SCRIPTS_DIR}/latency.py"
run_script "3/3  Bandbreite     (iperf3)"           "${SCRIPTS_DIR}/bandwidth.py"

# Optionaler vnstat-Snapshot
if grep -q '^VNSTAT_ENABLED="true"' "${CONFIG_FILE}" 2>/dev/null; then
    IFACE=$(grep "^VNSTAT_INTERFACE=" "${CONFIG_FILE}" | head -1 | cut -d'"' -f2 || echo "eth0")
    echo ""
    echo "------------------------------------------------------------"
    echo "  vnstat Traffic-Snapshot (${IFACE})"
    echo "------------------------------------------------------------"
    if command -v vnstat &>/dev/null; then
        vnstat -i "${IFACE}" --oneline 2>&1 | tee -a "${RUN_LOG}" || true
    else
        echo "  vnstat nicht installiert – installiere: apt install vnstat" | tee -a "${RUN_LOG}"
    fi
fi

# Log-Rotation: Logs älter als LOG_RETENTION_DAYS löschen
RETENTION=$(grep "^LOG_RETENTION_DAYS=" "${CONFIG_FILE}" 2>/dev/null | head -1 | cut -d'"' -f2 || echo "30")
find "${LOG_DIR}" -name "*.json" -mtime "+${RETENTION}" -delete 2>/dev/null || true
find "${LOG_DIR}" -name "*.log"  -mtime "+${RETENTION}" -delete 2>/dev/null || true

echo ""
echo "============================================================"
echo "  Lauf abgeschlossen : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Logs               : ${LOG_DIR}"
echo "============================================================"
echo ""
