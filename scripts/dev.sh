#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}✅${NC} $1"; }
error() { echo -e "${RED}❌${NC} $1"; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

COMMAND=${1:-help}

case "$COMMAND" in
    start)
        log "🐳 Starting Docker containers..."
        docker-compose up -d
        success "Containers started"
        sleep 3
        docker-compose ps
        ;;
    stop)
        log "⏹️  Stopping Docker containers..."
        docker-compose stop
        success "Containers stopped"
        ;;
    restart)
        log "🔄 Restarting Docker containers..."
        docker-compose restart
        success "Containers restarted"
        sleep 3
        docker-compose ps
        ;;
    logs)
        log "📋 All Logs"
        docker-compose logs -f --tail=50
        ;;
    logs-mqtt)
        log "📋 MQTT Logs"
        docker-compose logs -f mqtt-broker
        ;;
    logs-app)
        log "📋 App Logs"
        docker-compose logs -f home-automation
        ;;
    status)
        log "📊 Container Status"
        docker-compose ps
        ;;
    clean)
        log "🧹 Cleaning up..."
        docker-compose down -v
        success "Cleanup complete"
        ;;
    rebuild)
        log "🔨 Rebuilding..."
        docker-compose down
        docker-compose build --no-cache
        docker-compose up -d
        success "Rebuild complete"
        sleep 3
        docker-compose ps
        ;;
    shell-app)
        log "🐚 Entering shell..."
        docker exec -it home-automation-app bash
        ;;
    test)
        log "🧪 Testing MQTT..."
        docker exec home-mqtt-broker mosquitto_sub -h localhost -t "test" -C 1 -W 2 &
        sleep 2
        docker exec home-mqtt-broker mosquitto_pub -h localhost -t "test" -m "Test" || true
        success "MQTT test complete"
        ;;
    help)
        echo -e "${BLUE}Home Automation - Commands${NC}"
        echo ""
        echo "Commands:"
        echo "  start       - Start containers"
        echo "  stop        - Stop containers"
        echo "  restart     - Restart containers"
        echo "  logs        - Show all logs"
        echo "  logs-mqtt   - Show MQTT logs"
        echo "  logs-app    - Show app logs"
        echo "  status      - Show status"
        echo "  clean       - Remove containers"
        echo "  rebuild     - Rebuild image"
        echo "  shell-app   - Enter shell"
        echo "  test        - Test MQTT"
        echo "  help        - Show this help"
        ;;
    *)
        error "Unknown command: $COMMAND"
        exit 1
        ;;
esac
