#!/bin/bash
# run_all.sh – Führt alle Baseline-Monitoring-Skripte nacheinander aus.
#
# Verwendung:
#   sudo bash run_all.sh                                         # Automatisch (Systemd)
#   sudo bash run_all.sh --interactive                           # Sicherer Modus mit Bestätigung
#   sudo bash run_all.sh --config /pfad/zu/baseline-monitor.conf
#   sudo bash run_all.sh --interactive --preflight               # Mit Preflight-Check
#
# Modi:
#   Standard (ohne Flag) : Alle Tests laufen ohne Rückfrage (für Systemd-Timer)
#   --interactive         : Bestätigung vor jedem Schritt, Ergebnis-Prüfung dazwischen
#   --preflight           : Führt Preflight-Check vor dem ersten Test aus
#
# Wird automatisch vom Systemd-Timer aufgerufen (ohne --interactive).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config/baseline-monitor.conf"
SCRIPTS_DIR="${SCRIPT_DIR}/scripts"
INTERACTIVE=false
PREFLIGHT=false

# Argumente parsen
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)      CONFIG_FILE="$2"; shift 2 ;;
        --interactive) INTERACTIVE=true; shift ;;
        --preflight)   PREFLIGHT=true; shift ;;
        --help|-h)
            echo "Verwendung: sudo bash run_all.sh [--interactive] [--preflight] [--config PFAD]"
            echo ""
            echo "  --interactive  Bestätigung vor jedem Schritt (sicherer Modus)"
            echo "  --preflight    Preflight-Check vor dem ersten Test"
            echo "  --config PFAD  Pfad zur baseline-monitor.conf"
            exit 0
            ;;
        *) echo "Unbekannte Option: $1 (--help für Hilfe)"; exit 1 ;;
    esac
done

# ── Hilfsfunktionen ────────────────────────────────────────────

confirm() {
    # Im nicht-interaktiven Modus immer ja
    if [ "${INTERACTIVE}" = false ]; then
        return 0
    fi
    local prompt="$1"
    local default="${2:-J}"
    local suffix
    if [ "${default}" = "J" ]; then
        suffix="[J/n]"
    else
        suffix="[j/N]"
    fi
    while true; do
        read -r -p "  ${prompt} ${suffix}: " answer
        answer="${answer:-${default}}"
        case "${answer,,}" in
            j|ja|y|yes) return 0 ;;
            n|nein|no)  return 1 ;;
            *) echo "  Bitte J oder N eingeben." ;;
        esac
    done
}

pause_review() {
    # Im nicht-interaktiven Modus nichts tun
    if [ "${INTERACTIVE}" = false ]; then
        return
    fi
    echo ""
    echo "  ── Ergebnis-Prüfung ──"
    echo "  Prüfe die Konsolenausgabe oben auf Plausibilität."
    if ! confirm "Ergebnis plausibel? Weiter zum nächsten Test?"; then
        echo "  Abgebrochen durch Benutzer."
        echo "  Bisherige Logs findest du in: ${LOG_DIR}"
        exit 0
    fi
}

# ── Konfiguration prüfen ──────────────────────────────────────

if [ ! -f "${CONFIG_FILE}" ]; then
    echo "FEHLER: Konfigurationsdatei nicht gefunden: ${CONFIG_FILE}"
    echo ""
    echo "Optionen:"
    echo "  1. Setup-Wizard starten: python3 ${SCRIPTS_DIR}/setup_wizard.py"
    echo "  2. Manuell kopieren:     cp baseline-monitor/config/baseline-monitor.conf ${CONFIG_FILE}"
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
echo "  Gestartet     : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Konfiguration : ${CONFIG_FILE}"
echo "  Modus         : $([ "${INTERACTIVE}" = true ] && echo 'INTERAKTIV (Bestätigung pro Schritt)' || echo 'Automatisch')"
echo "  Ausgabe       : ${RUN_LOG}"
echo "============================================================"

# ── Preflight-Check (optional) ────────────────────────────────

if [ "${PREFLIGHT}" = true ]; then
    echo ""
    echo "------------------------------------------------------------"
    echo "  Preflight-Check"
    echo "------------------------------------------------------------"
    python3 "${SCRIPTS_DIR}/preflight.py" --config "${CONFIG_FILE}" 2>&1 | tee -a "${RUN_LOG}"
    PREFLIGHT_EXIT=${PIPESTATUS[0]}
    if [ "${PREFLIGHT_EXIT}" -eq 1 ]; then
        echo ""
        echo "  Preflight-Check hat kritische Fehler gefunden."
        if ! confirm "Trotzdem fortfahren?"; then
            echo "  Abgebrochen. Behebe die Fehler und versuche es erneut."
            exit 1
        fi
    fi
    if [ "${INTERACTIVE}" = true ]; then
        pause_review
    fi
fi

# ── Skript-Ausführung ─────────────────────────────────────────

run_script() {
    local label="$1"
    local script="$2"

    # Im interaktiven Modus: vorher fragen
    if [ "${INTERACTIVE}" = true ]; then
        echo ""
        if ! confirm "${label} jetzt ausführen?"; then
            echo "  Übersprungen: ${label}" | tee -a "${RUN_LOG}"
            return 0
        fi
    fi

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

    # Im interaktiven Modus: Ergebnis prüfen lassen
    if [ "${INTERACTIVE}" = true ]; then
        pause_review
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

# ── Log-Übersicht (interaktiv) ─────────────────────────────────

if [ "${INTERACTIVE}" = true ]; then
    echo ""
    echo "------------------------------------------------------------"
    echo "  Log-Dateien dieses Laufs"
    echo "------------------------------------------------------------"
    ls -lh "${LOG_DIR}/"*"${TIMESTAMP}"* 2>/dev/null || echo "  (keine Dateien mit Timestamp ${TIMESTAMP} gefunden)"
    echo ""
    echo "  Alle Logs: ls -lh ${LOG_DIR}/"
    echo ""
    if confirm "Systemd-Timer jetzt aktivieren? (Automatisierung scharfschalten)"; then
        if command -v systemctl &>/dev/null; then
            systemctl enable --now baseline-monitor.timer 2>&1
            echo "  Timer aktiviert! Status:"
            systemctl list-timers baseline-monitor.timer 2>&1 || true
        else
            echo "  systemctl nicht verfügbar (kein Systemd?)."
        fi
    else
        echo "  Timer NICHT aktiviert. Manuell aktivieren:"
        echo "    sudo systemctl enable --now baseline-monitor.timer"
    fi
fi

echo ""
echo "============================================================"
echo "  Lauf abgeschlossen : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Logs               : ${LOG_DIR}"
if [ "${INTERACTIVE}" = true ]; then
echo "  Nächste Analyse    : python3 ${SCRIPTS_DIR}/analyze.py --config ${CONFIG_FILE}"
fi
echo "============================================================"
echo ""
