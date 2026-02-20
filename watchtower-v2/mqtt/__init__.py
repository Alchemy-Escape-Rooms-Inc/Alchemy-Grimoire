"""
WatchTower V2 MQTT Client
===========================
Handles broker connection, device ping/pong, message filtering, and live feed.
Ported from V1 system_checker.py with cleaner architecture.
"""

import re
import time
import uuid
import threading
import logging
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable

import paho.mqtt.client as mqtt

import config

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    TESTING = "testing"


class DeviceType(Enum):
    BAC = "bac"
    ESP32 = "esp32"


@dataclass
class Device:
    name: str
    device_type: DeviceType
    topic_base: str
    icon: str = "📡"
    color: str = "#4A90D9"
    room: str = ""
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_test: Optional[datetime] = None
    response_time_ms: Optional[int] = None
    last_error: Optional[str] = None
    commands: list = field(default_factory=lambda: ["PING", "STATUS", "RESET", "PUZZLE_RESET"])
    needs_protocol: bool = False


class MQTTClient:
    """Manages MQTT connection, device health checking, and message feed."""

    def __init__(self, on_message_callback: Optional[Callable] = None):
        self.devices: Dict[str, Device] = {}
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.lock = threading.Lock()

        # Message feed (in-memory ring buffer for live UI)
        self.message_feed: List[dict] = []
        self.max_feed_messages = config.MAX_MESSAGES

        # Smart filtering state
        self.recent_sent: List[tuple] = []
        self.last_values: Dict[str, float] = {}
        self.last_payloads: Dict[str, str] = {}

        # External callback for new messages (used by SSE)
        self.on_message_callback = on_message_callback

        # Load devices from config
        self._load_devices()

    def _load_devices(self):
        """Load device registry from config."""
        for bac in config.BAC_CONTROLLERS:
            self.devices[bac["name"]] = Device(
                name=bac["name"],
                device_type=DeviceType.BAC,
                topic_base=bac["name"],
                icon=bac.get("icon", "🎛️"),
                color=bac.get("color", "#4A90D9"),
                room="Zone Controller"
            )

        for esp in config.ESP32_DEVICES:
            self.devices[esp["name"]] = Device(
                name=esp["name"],
                device_type=DeviceType.ESP32,
                topic_base=esp.get("topic", esp["name"]),
                icon=esp.get("icon", "📡"),
                color=esp.get("color", "#4A90D9"),
                room=esp.get("room", ""),
                commands=esp.get("commands", ["PING", "STATUS", "RESET", "PUZZLE_RESET"]),
                needs_protocol=esp.get("needs_protocol", False)
            )

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            self.client = mqtt.Client(client_id=f"watchtower_v2_{uuid.uuid4().hex[:8]}")
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            logger.info(f"Connecting to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}")
            self.client.connect(config.MQTT_BROKER, config.MQTT_PORT, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            # Subscribe to everything for the live feed
            client.subscribe("#")
            # Specific subscriptions for device responses
            client.subscribe("MermaidsTale/+/status")
            client.subscribe("MermaidsTale/+/command")
            client.subscribe("+/get/#")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8").strip()
        except:
            payload = str(msg.payload)

        now = datetime.now()

        # Add to feed if it passes filters
        if self._should_show_message(topic, payload):
            device_name = self._extract_device_name(topic)
            message = {
                "timestamp": now.strftime("%H:%M:%S"),
                "timestamp_full": now.isoformat(),
                "direction": "RX",
                "topic": topic,
                "payload": payload[:200] if payload else "",
                "device": device_name
            }
            with self.lock:
                self.message_feed.insert(0, message)
                if len(self.message_feed) > self.max_feed_messages:
                    self.message_feed.pop()

            if self.on_message_callback:
                try:
                    self.on_message_callback(message)
                except:
                    pass

        # Process device health responses
        self._process_device_response(topic, payload, now)

    def _process_device_response(self, topic: str, payload: str, now: datetime):
        """Check if message is a response to a ping or a BAC heartbeat."""
        with self.lock:
            for device_name, device in self.devices.items():
                # BAC passive heartbeat monitoring
                if device.device_type == DeviceType.BAC:
                    expected_prefix = f"{device.topic_base}/get/"
                    if topic.lower().startswith(expected_prefix.lower()) or \
                       (device.topic_base.lower() in topic.lower() and "/get/" in topic.lower()):
                        if device.status != DeviceStatus.ONLINE:
                            logger.info(f"✓ BAC {device_name} heartbeat detected")
                        device.status = DeviceStatus.ONLINE
                        device.last_error = None
                        device.last_test = now
                        continue

                # ESP32 - only process if we're waiting for a response
                if device.status != DeviceStatus.TESTING:
                    continue

                is_match = False
                if device.device_type == DeviceType.ESP32:
                    command_topic = f"MermaidsTale/{device.topic_base}/command"
                    status_topic = f"MermaidsTale/{device.topic_base}/status"

                    if (topic == command_topic and payload == "PONG") or \
                       (topic == status_topic and payload == "PONG") or \
                       (topic == status_topic):
                        is_match = True

                if is_match:
                    if device.last_test:
                        response_ms = int((now - device.last_test).total_seconds() * 1000)
                        device.response_time_ms = response_ms
                    device.status = DeviceStatus.ONLINE
                    device.last_error = None
                    logger.info(f"✓ {device_name} responded ({device.response_time_ms}ms)")
                    return

    def _should_show_message(self, topic: str, payload: str) -> bool:
        """Smart filtering - ported from V1."""
        # Only show device-related topics
        if not ("MermaidsTale" in topic or
                any(d in topic for d in ["Shattic", "Captain", "Cove", "Jungle"])):
            return False

        # Hidden topics (heartbeats)
        if any(pattern in topic for pattern in config.HIDDEN_TOPICS):
            return False

        # Echo suppression
        with self.lock:
            for sent_topic, sent_payload in self.recent_sent:
                if sent_topic == topic and sent_payload == payload:
                    self.recent_sent.remove((sent_topic, sent_payload))
                    return False

        # Duplicate suppression
        if any(pattern in topic for pattern in config.DEDUP_TOPICS):
            with self.lock:
                last = self.last_payloads.get(topic)
                self.last_payloads[topic] = payload
                if last == payload:
                    return False

        # Delta filtering for sensor data
        if any(pattern in topic for pattern in config.DELTA_TOPICS):
            try:
                numbers = re.findall(r'[-+]?\d*\.?\d+', payload)
                if numbers:
                    value = float(numbers[-1])
                    with self.lock:
                        last_val = self.last_values.get(topic)
                        if last_val is not None and abs(value - last_val) < config.DELTA_THRESHOLD:
                            return False
                        self.last_values[topic] = value
            except (ValueError, IndexError):
                pass

        return True

    def _extract_device_name(self, topic: str) -> Optional[str]:
        """Extract device name from MQTT topic."""
        parts = topic.split("/")
        if len(parts) > 1 and parts[0] == "MermaidsTale":
            return parts[1]
        elif len(parts) > 0:
            return parts[0]
        return None

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def ping_device(self, device_name: str) -> bool:
        """Send a ping to a specific device."""
        if device_name not in self.devices or not self.connected:
            return False

        device = self.devices[device_name]
        with self.lock:
            device.status = DeviceStatus.TESTING
            device.last_test = datetime.now()
            device.response_time_ms = None

        if device.device_type == DeviceType.ESP32:
            topic = f"MermaidsTale/{device.topic_base}/command"
            self.client.publish(topic, "PING")
            self._track_sent(topic, "PING")
            logger.info(f"→ Pinged {device_name} on {topic}")
        else:
            logger.info(f"→ Waiting for BAC {device_name} heartbeat")

        return True

    def ping_all(self):
        """Ping all devices."""
        for name in self.devices:
            self.ping_device(name)

    def send_command(self, device_name: str, command: str) -> dict:
        """Send a command to a device."""
        if device_name not in self.devices:
            return {"error": f"Unknown device: {device_name}"}
        if not self.connected:
            return {"error": "MQTT not connected"}

        device = self.devices[device_name]

        if device.device_type == DeviceType.ESP32:
            topic = f"MermaidsTale/{device.topic_base}/command"
        else:
            topic = f"{device.topic_base}/set/{command.lower()}"

        self.client.publish(topic, command)
        self._track_sent(topic, command)

        # Add TX to feed
        message = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_full": datetime.now().isoformat(),
            "direction": "TX",
            "topic": topic,
            "payload": command,
            "device": device_name
        }
        with self.lock:
            self.message_feed.insert(0, message)
            if len(self.message_feed) > self.max_feed_messages:
                self.message_feed.pop()

        return {"device": device_name, "command": command, "topic": topic, "sent": True}

    def check_timeouts(self):
        """Mark devices as offline if they didn't respond in time."""
        now = datetime.now()
        with self.lock:
            for device in self.devices.values():
                if device.status == DeviceStatus.TESTING and device.last_test:
                    elapsed = (now - device.last_test).total_seconds()
                    timeout = config.BAC_PING_TIMEOUT if device.device_type == DeviceType.BAC else config.ESP32_PING_TIMEOUT
                    if elapsed > timeout:
                        device.status = DeviceStatus.OFFLINE
                        device.last_error = "No response"

    def get_status_summary(self) -> dict:
        """Get full status summary for API."""
        self.check_timeouts()
        summary = {
            "broker_connected": self.connected,
            "broker_host": config.MQTT_BROKER,
            "broker_port": config.MQTT_PORT,
            "timestamp": datetime.now().isoformat(),
            "devices": {},
            "counts": {"online": 0, "offline": 0, "unknown": 0, "testing": 0}
        }

        with self.lock:
            for name, device in self.devices.items():
                summary["devices"][name] = {
                    "type": device.device_type.value,
                    "status": device.status.value,
                    "icon": device.icon,
                    "color": device.color,
                    "room": device.room,
                    "topic": device.topic_base,
                    "last_test": device.last_test.isoformat() if device.last_test else None,
                    "response_ms": device.response_time_ms,
                    "error": device.last_error,
                    "commands": device.commands,
                    "needs_protocol": device.needs_protocol,
                    "grimoire_slug": config.GRIMOIRE_SLUG_MAP.get(name)
                }
                summary["counts"][device.status.value] += 1

        return summary

    def get_feed(self, limit=50) -> list:
        """Get recent messages from the feed."""
        with self.lock:
            return self.message_feed[:limit]

    def _track_sent(self, topic, payload):
        """Track sent messages for echo suppression."""
        with self.lock:
            self.recent_sent.insert(0, (topic, payload))
            if len(self.recent_sent) > 20:
                self.recent_sent.pop()
