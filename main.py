#!/usr/bin/env python3
"""
Home Automation Main Application
"""

import sys
import signal
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.logging_setup import setup_logging
from src.mqtt_client import MQTTClient
from config.config import LOG_LEVEL

# Setup logging
logger = setup_logging()

class HomeAutomation:
    """Main Home Automation Application"""
    
    def __init__(self):
        self.mqtt = MQTTClient()
        logger.info("🏠 Home Automation System initialisiert")
    
    def start(self):
        """Anwendung starten"""
        logger.info("🚀 Home Automation startet...")
        try:
            self.mqtt.connect()
            logger.info("✅ System läuft - Drücke Ctrl+C zum Beenden")
            signal.pause()
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            logger.error(f"❌ Fehler: {e}")
            self.stop()
    
    def stop(self):
        """Anwendung stoppen"""
        logger.info("⏹️ Home Automation wird beendet...")
        self.mqtt.disconnect()
        logger.info("👋 Auf Wiedersehen!")

if __name__ == "__main__":
    app = HomeAutomation()
    app.start()
