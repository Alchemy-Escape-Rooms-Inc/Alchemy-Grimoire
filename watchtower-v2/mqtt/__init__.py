"""
WatchTower V2 MQTT Client
===========================
Handles broker connection, device ping/pong, message filtering, and live feed.
Ported from V1 system_checker.py with cleaner architecture.
"""

import os
import re
import time
import uuid
import threading
import logging
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable

import paho.mqtt.client as mqtt

import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# MQTT SESSION LOGGING
# ─────────────────────────────────────────────
# One .txt per Watchtower process boot, named mqtt_YYYY-MM-DD_HHMMSS.txt,
# written to watchtower-v2/logs/. Files older than 24h are purged on startup.

MQTT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)
MQTT_LOG_PREFIX = "mqtt_"
MQTT_LOG_SUFFIX = ".txt"
MQTT_LOG_RETENTION = timedelta(hours=24)
MQTT_LOG_NAME_FORMAT = "%Y-%m-%d_%H%M%S"


def _purge_old_mqtt_logs():
    """Delete session logs whose filename timestamp is older than 24h."""
    if not os.path.isdir(MQTT_LOG_DIR):
        return
    cutoff = datetime.now() - MQTT_LOG_RETENTION
    for name in os.listdir(MQTT_LOG_DIR):
        if not (name.startswith(MQTT_LOG_PREFIX) and name.endswith(MQTT_LOG_SUFFIX)):
            continue
        stem = name[len(MQTT_LOG_PREFIX):-len(MQTT_LOG_SUFFIX)]
        try:
            file_ts = datetime.strptime(stem, MQTT_LOG_NAME_FORMAT)
        except ValueError:
            continue
        if file_ts < cutoff:
            try:
                os.remove(os.path.join(MQTT_LOG_DIR, name))
                logger.info(f"Purged old MQTT log: {name}")
            except OSError as e:
                logger.warning(f"Could not purge {name}: {e}")


def _open_mqtt_session_log():
    """Create logs/ if missing, purge stale files, open a new session file."""
    os.makedirs(MQTT_LOG_DIR, exist_ok=True)
    _purge_old_mqtt_logs()
    stamp = datetime.now().strftime(MQTT_LOG_NAME_FORMAT)
    path = os.path.join(MQTT_LOG_DIR, f"{MQTT_LOG_PREFIX}{stamp}{MQTT_LOG_SUFFIX}")
    f = open(path, "a", encoding="utf-8", buffering=1)  # line-buffered
    f.write(f"# Watchtower MQTT session log — started {datetime.now().isoformat()}\n")
    logger.info(f"MQTT session log: {path}")
    return f, path


# Accept a PONG/status reply this long after a ping was sent, even if the
# ping already "timed out" — slow-waking boards answer late, not never.
LATE_PONG_GRACE_S = 60


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

        # Systems-group signal tracking: last time we saw evidence each
        # infrastructure system is alive on MQTT (used by /api/status systems).
        #   ai_brain    -> any MermaidsTale/RedBeard/* traffic (AI Character process)
        #   ai_launcher -> MermaidsTale/AILauncher/* heartbeat (ai_launcher.py —
        #                  the process that receives the Reset Brain command; if
        #                  it's dead, the Reset button publishes into the void)
        #   m3          -> M3/Stories/AMT/State == "Running" (game runner)
        self.system_signals: Dict[str, dict] = {
            "ai_brain":    {"last_seen": None, "detail": None},
            "ai_launcher": {"last_seen": None, "detail": None},
            "m3":          {"last_seen": None, "detail": None},
            #   unreal_room -> MermaidsTale/Unreal/RoomStatus heartbeat (5s from
            #                  the packaged game): {"map":..,"audioRoom":..} —
            #                  which map/room Unreal is ACTUALLY sitting in.
            #                  Drives the pre-game room-confirmation light.
            "unreal_room": {"last_seen": None, "detail": None},
        }

        # Last retained WatchTower/ShipCameraTuning payload (JSON string) —
        # seeded by the broker's retained replay on subscribe, updated on every
        # publish. Read by /api/ship-camera GET for the /game sliders.
        self.ship_camera_tuning: str = ""

        # Pre-game readiness tracking (see routes/api.py _pregame_checks):
        #   retained_landmines  topic -> payload for retained GameStart/command/
        #                       reset messages still sitting on the broker
        #   prop_states         topic -> {payload, ts} for the room-reset topics
        #                       in config.PREGAME_PROP_STATES
        #   boot_events         device -> [datetime] of reboot evidence (uptime
        #                       went backwards or a boot/reboot log line)
        self.retained_landmines: Dict[str, str] = {}
        self.prop_states: Dict[str, dict] = {}
        self.boot_events: Dict[str, List[datetime]] = {}
        self._last_uptimes: Dict[str, float] = {}
        self._pregame_prop_topics = {row["topic"] for row in config.PREGAME_PROP_STATES}

        # External callback for new messages (used by SSE)
        self.on_message_callback = on_message_callback

        # Per-session raw MQTT log file (purges files >24h old on boot)
        try:
            self._session_log_file, self._session_log_path = _open_mqtt_session_log()
        except Exception as e:
            logger.error(f"Failed to open MQTT session log: {e}")
            self._session_log_file = None
            self._session_log_path = None

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
            # connect_async + loop_start: paho keeps retrying in the background if the
            # broker isn't up yet (START bat race, 2026-07-02: a failed one-shot connect
            # left WatchTower blind all night — 0-byte mqtt_*.txt wire log).
            self.client.connect_async(config.MQTT_BROKER, config.MQTT_PORT, 60)
            self.client.reconnect_delay_set(min_delay=1, max_delay=10)
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

        # Raw session log — captures EVERYTHING pre-filter (so compass-style
        # diagnostics aren't hidden by _should_show_message).
        if self._session_log_file is not None:
            try:
                ts = now.strftime("%H:%M:%S.%f")[:-3]
                self._session_log_file.write(f"[{ts}] {topic} | {payload}\n")
            except Exception:
                pass

        # Systems-group signal capture (pre-filter, so quiet heartbeats count).
        self._note_system_signal(topic, payload, now)

        # Ship-camera tuning readback: the broker replays the retained value on
        # our '#' subscribe, so the /game sliders always show what the game is
        # actually using — even right after a WatchTower restart.
        if topic == "WatchTower/ShipCameraTuning" and payload:
            self.ship_camera_tuning = payload

        # Pre-game readiness capture (retained landmines, prop states, reboots).
        try:
            self._note_pregame(topic, payload, now, bool(msg.retain))
        except Exception:  # noqa: BLE001 - never let readiness break the feed
            pass

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

                # ESP32 - process if we're waiting for a response, OR if the
                # board answers LATE. Observed 2026-07-10 (BarrelPiston): a
                # power-saving ESP32 took 12s to process the first PING after
                # idle (then ~200ms on later pings), so the 3s timeout stamped
                # it offline and its perfectly good PONG was discarded here.
                # A matching response within the grace window after a failed
                # ping is proof of life — flip it back online.
                if device.status != DeviceStatus.TESTING:
                    late_ok = (
                        device.status == DeviceStatus.OFFLINE
                        and device.last_test is not None
                        and (now - device.last_test).total_seconds() <= LATE_PONG_GRACE_S
                    )
                    if not late_ok:
                        continue

                is_match = False
                if device.device_type == DeviceType.ESP32:
                    command_topic = f"MermaidsTale/{device.topic_base}/command"
                    status_topic = f"MermaidsTale/{device.topic_base}/status"
                    # 2026-07-09: some boards (TridentCabinet, CaptainsCuffs)
                    # answer PING with PONG on their /message topic, not
                    # /status or /command. Without this they only "passed" a
                    # ping sweep by racing their periodic ONLINE heartbeat on
                    # /status — a dead firmware with a live heartbeat looked
                    # healthy. PONG-only match here: /message also carries
                    # general log lines, which must NOT count as a ping reply.
                    message_topic = f"MermaidsTale/{device.topic_base}/message"

                    if (topic == command_topic and payload == "PONG") or \
                       (topic == status_topic and payload == "PONG") or \
                       (topic == status_topic) or \
                       (topic == message_topic and payload.upper() == "PONG"):
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

    def _note_system_signal(self, topic: str, payload: str, now: datetime):
        """Record live evidence that infrastructure systems are alive.
        Used by the dashboard's Systems group (separate from device tiles)."""
        # AI Character brain: any RedBeard traffic means the AI process is up
        # and publishing (e.g. MermaidsTale/RedBeard/Talking).
        if topic.startswith("MermaidsTale/RedBeard"):
            sig = self.system_signals["ai_brain"]
            sig["last_seen"] = now
            sig["detail"] = topic.split("/", 2)[-1]
        # ai_launcher.py heartbeat — proves the Reset Brain command has a
        # live receiver. Deliberately NOT under RedBeard/* so a dead brain
        # can't be masked by a healthy launcher (and vice versa).
        elif topic.startswith("MermaidsTale/AILauncher"):
            sig = self.system_signals["ai_launcher"]
            sig["last_seen"] = now
            sig["detail"] = payload or "alive"
        # M3 / Mythric game runner: State=Running on the AMT story.
        elif topic == "M3/Stories/AMT/State":
            sig = self.system_signals["m3"]
            sig["last_seen"] = now
            sig["detail"] = payload
        # Unreal room heartbeat: raw JSON payload, parsed by the API layer.
        elif topic == "MermaidsTale/Unreal/RoomStatus":
            sig = self.system_signals["unreal_room"]
            sig["last_seen"] = now
            sig["detail"] = payload

    # Uptime formats seen on the wire: JungleDoor "18:55:04", BarrelPiston
    # "450", Cannon status "...Uptime:68117833ms...", CoveDoor "...UP325114s...".
    _UPTIME_MS_RE = re.compile(r"Uptime:(\d+)ms", re.IGNORECASE)
    _UPTIME_S_RE = re.compile(r"\bUP(\d+)s\b", re.IGNORECASE)
    _HMS_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$")

    def _parse_uptime_s(self, topic: str, payload: str) -> Optional[float]:
        """Best-effort seconds-of-uptime from a message, else None."""
        if topic.endswith("/uptime"):
            m = self._HMS_RE.match(payload)
            if m:
                h, mi, s = (int(x) for x in m.groups())
                return h * 3600 + mi * 60 + s
            if payload.isdigit():
                return float(payload)
            return None
        m = self._UPTIME_MS_RE.search(payload)
        if m:
            return int(m.group(1)) / 1000.0
        m = self._UPTIME_S_RE.search(payload)
        if m:
            return float(m.group(1))
        return None

    def _note_pregame(self, topic: str, payload: str, now: datetime, retained: bool):
        """Track the signals behind the dashboard's Pre-Game Readiness banner."""
        # 1. Retained landmines. The retain flag is only set on retained-store
        #    replay at (re)subscribe — a live publish reaches an already-
        #    subscribed client with retain=0 even when the publisher set it
        #    (MQTT-3.3.1-9). So: add only on retained delivery, but pop on ANY
        #    empty payload — an empty publish on a landmine topic is only ever
        #    a wipe, and gating the pop on the flag left cleared landmines
        #    flagged until WatchTower reconnected.
        if topic in config.PREGAME_LANDMINE_TOPICS \
                or any(topic.endswith(s) for s in config.PREGAME_LANDMINE_SUFFIXES):
            with self.lock:
                if not payload:
                    self.retained_landmines.pop(topic, None)
                elif retained:
                    self.retained_landmines[topic] = payload

        # 2. Prop start-position states (room-reset check). Skip transient
        #    command replies — CompassTrio answers PING/RESET on its /status
        #    topic, and a stored "PONG" would mask the real SOLVED/UNSOLVED
        #    state until the next 5-min heartbeat.
        if topic in self._pregame_prop_topics:
            if payload.strip().lower() not in config.PREGAME_PROP_TRANSIENT_PAYLOADS:
                with self.lock:
                    self.prop_states[topic] = {"payload": payload, "ts": now}

        # 3. Reboot evidence: an explicit boot/reboot log line, or a device
        #    uptime that went backwards. Live messages only — a retained boot
        #    line replayed on our own reconnect is not a fresh reboot.
        if retained:
            return
        boot = False
        low = payload.lower()
        if "boot complete" in low or "rebooting" in low:
            boot = True
        else:
            up = self._parse_uptime_s(topic, payload)
            if up is not None:
                last = self._last_uptimes.get(topic)
                self._last_uptimes[topic] = up
                if last is not None and up + 30 < last:
                    boot = True
        if boot:
            device = self._extract_device_name(topic) or topic
            cutoff = now - timedelta(seconds=config.PREGAME_BOOTLOOP_WINDOW_S)
            with self.lock:
                events = [t for t in self.boot_events.get(device, []) if t > cutoff]
                events.append(now)
                self.boot_events[device] = events

    def refresh_retained_landmines(self):
        """Rebuild the landmine dict from the broker's actual retained store.
        Clearing it and resubscribing makes the broker replay every retained
        message with retain=1, so anything wiped (or planted) while we were
        already connected is reconciled within a second or two."""
        with self.lock:
            self.retained_landmines.clear()
        if self.client and self.connected:
            try:
                self.client.unsubscribe("#")
                self.client.subscribe("#")
            except Exception:  # noqa: BLE001 - a failed refresh just leaves the dict empty
                logger.exception("Retained-landmine resubscribe failed")

    def get_pregame_signals(self) -> dict:
        """Snapshot for the Pre-Game Readiness checks in /api/status."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=config.PREGAME_BOOTLOOP_WINDOW_S)
        with self.lock:
            landmines = dict(self.retained_landmines)
            props = {
                t: {"payload": s["payload"], "age_s": (now - s["ts"]).total_seconds()}
                for t, s in self.prop_states.items()
            }
            boot_loops = {}
            for dev, times in self.boot_events.items():
                recent = [t for t in times if t > cutoff]
                if len(recent) >= config.PREGAME_BOOTLOOP_COUNT:
                    boot_loops[dev] = {
                        "count": len(recent),
                        "last_age_s": (now - max(recent)).total_seconds(),
                    }
        return {"landmines": landmines, "props": props, "boot_loops": boot_loops}

    def get_system_signals(self) -> dict:
        """Snapshot of system signals with seconds-since-last-seen, for the API."""
        now = datetime.now()
        out = {}
        with self.lock:
            for key, sig in self.system_signals.items():
                last = sig["last_seen"]
                out[key] = {
                    "last_seen": last.isoformat() if last else None,
                    "age_s": (now - last).total_seconds() if last else None,
                    "detail": sig["detail"],
                }
        return out

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

    def publish_raw(self, topic: str, payload: str, retain: bool = False) -> dict:
        """Publish an arbitrary topic/payload (not tied to the device registry).
        Used for infrastructure commands like the AI-brain restart, which target
        a listener on the AI machine rather than a registered ESP32/BAC device.
        retain=True persists the value on the broker (ship-camera tuning)."""
        if not self.connected:
            return {"error": "MQTT not connected"}

        self.client.publish(topic, payload, retain=retain)
        self._track_sent(topic, payload)

        message = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "timestamp_full": datetime.now().isoformat(),
            "direction": "TX",
            "topic": topic,
            "payload": payload,
            "device": "WatchTower",
        }
        with self.lock:
            self.message_feed.insert(0, message)
            if len(self.message_feed) > self.max_feed_messages:
                self.message_feed.pop()

        return {"topic": topic, "payload": payload, "sent": True}

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
