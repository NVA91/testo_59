import logging
from paho.mqtt import client as mqtt_client
from config.config import MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASSWORD

logger = logging.getLogger(__name__)

class MQTTClient:
    """MQTT Client für Home Automation"""
    
    def __init__(self):
        self.client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.V1)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
    def on_connect(self, client, userdata, flags, rc):
        """Callback für Verbindung"""
        if rc == 0:
            logger.info("✅ MQTT verbunden!")
            self.client.subscribe("home/+/+")
        else:
            logger.error(f"❌ MQTT Fehler: {rc}")
    
    def on_message(self, client, userdata, msg):
        """Callback für Nachrichten"""
        logger.info(f"📨 {msg.topic}: {msg.payload.decode()}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback für Trennung"""
        if rc != 0:
            logger.warning(f"⚠️ Ungeplante Trennung: {rc}")
    
    def connect(self):
        """Verbindung herstellen"""
        try:
            self.client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
            logger.info(f"🔌 Verbinde zu {MQTT_BROKER}:{MQTT_PORT}")
        except Exception as e:
            logger.error(f"❌ Verbindungsfehler: {e}")
    
    def publish(self, topic, payload):
        """Nachricht senden"""
        self.client.publish(topic, payload)
        logger.info(f"📤 {topic}: {payload}")
    
    def disconnect(self):
        """Verbindung beenden"""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("🔌 Verbindung beendet")
