"""
Retained-Command Watchdog
=========================
Erases poison retained MQTT messages 24/7, sweeper or no sweeper.

WHY THIS EXISTS (2026-08-08)
----------------------------
The AI stack's gamestart_retained_guard.py / game_end_retained_sweeper.py only
run while a game session is up (START_ESCAPE_ROOM.bat starts them, STOP kills
them). But M3 keeps running for days, and any reset it does off-hours can plant
retained commands with nobody around to clean them. Observed 2026-08-08 ~01:40:
retained OPENCABINET on TridentCabinet/command reboot-looped the board every
~6s (latch relay clicking the whole time), and retained OPEN + maglock UNLOCK
on CoveDoor replayed on every WiFi reconnect (motor 12s to safety timeout,
maglock clunking) — for HOURS, until a manual clear_retained_mqtt.py run.

WatchTower is the one process that is always up, so the standing defense lives
here: any retained message on a device /command, /reset, or /maglock topic is
erased the moment this watchdog sees it.

WHAT COUNTS AS POISON
---------------------
Topics under MermaidsTale/ ending in a RETAINED_WATCHDOG_SUFFIXES suffix
(/command, /reset, /maglock). Commands are one-shot by contract — M3 publishes
them non-retained; a *retained* one is always a bug (the M3 post-GameReset
retained race, or a stray `mosquitto_pub -r`). MermaidsTale/GameStart is
deliberately NOT covered: ai_launcher honors a retained GameStart as its
late-start rescue, and gamestart_retained_guard.py owns erasing it in-session.

HOW IT CATCHES NEW PLANTS (the retain-flag trap)
------------------------------------------------
Per MQTT-3.3.1-9 a live publish reaches an already-subscribed client with
retain=0 even when the publisher set retain=1 — the flag is only set on
retained-STORE replay at (re)subscribe. So a persistent subscription alone
would never see a landmine planted while we're connected. The watchdog
therefore re-subscribes every RETAINED_WATCHDOG_SWEEP_S seconds, forcing the
broker to replay the retained store for the watched patterns; anything poison
in the replay gets an empty retained publish (MQTT-3.3.1-6: erases the store).
Worst-case lifetime of a fresh landmine is one sweep interval, instead of
"until someone runs the clear script".

Erase echoes can't loop: deleting a topic's store means it is not replayed on
the next resubscribe, and our own zero-byte publish arrives retain=0 (ignored).
The main WatchTower client sees the same empty publish and pops the topic from
its pre-game landmine dict automatically.
"""

import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime

import paho.mqtt.client as mqtt

import config

logger = logging.getLogger(__name__)


class RetainedCommandWatchdog:
    """Own-client watchdog: watch, log, and erase poison retained commands."""

    def __init__(self):
        self.client = None
        self.connected = False
        self.lock = threading.Lock()
        # Recent erasures for the API / dashboard: newest first.
        self.erasures = deque(maxlen=config.RETAINED_WATCHDOG_HISTORY)
        # topic -> erase count since boot; a climbing count means something is
        # actively re-planting (M3 mid-reset race) rather than a one-off stray.
        self.erase_counts = {}
        self._sweep_thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ MQTT

    def _patterns(self):
        prefix = config.RETAINED_WATCHDOG_PREFIX
        return [f"{prefix}+{suffix}" for suffix in config.RETAINED_WATCHDOG_SUFFIXES]

    def _is_poison_topic(self, topic: str) -> bool:
        if not topic.startswith(config.RETAINED_WATCHDOG_PREFIX):
            return False
        return any(topic.endswith(s) for s in config.RETAINED_WATCHDOG_SUFFIXES)

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            logger.error(f"Retained watchdog: connect failed rc={rc}")
            return
        self.connected = True
        for pattern in self._patterns():
            client.subscribe(pattern)
        logger.info(f"Retained watchdog: connected, watching {self._patterns()}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            logger.warning(f"Retained watchdog: disconnected rc={rc}, paho will retry")

    def _on_message(self, client, userdata, msg):
        # Only retained-store replays matter. Live commands (retain=0) are the
        # show doing its job; our own erase echoes are retain=0 and empty.
        if not msg.retain or not msg.payload:
            return
        topic = msg.topic
        if not self._is_poison_topic(topic):
            return
        try:
            payload = msg.payload.decode("utf-8", "replace").strip()
        except Exception:  # noqa: BLE001
            payload = repr(msg.payload)
        # MQTT-3.3.1-6: retained publish with zero-length payload drops the
        # broker's retained message for the topic.
        client.publish(topic, payload=None, qos=1, retain=True)
        with self.lock:
            self.erase_counts[topic] = self.erase_counts.get(topic, 0) + 1
            count = self.erase_counts[topic]
            self.erasures.appendleft({
                "ts": datetime.now().isoformat(),
                "topic": topic,
                "payload": payload[:200],
                "count": count,
            })
        if count >= config.RETAINED_WATCHDOG_REPLANT_ALERT:
            logger.warning(
                f"Retained watchdog: ERASED retained '{payload}' on {topic} "
                f"({count}x since boot — something keeps re-planting it)")
        else:
            logger.warning(f"Retained watchdog: ERASED retained '{payload}' on {topic}")

    # ----------------------------------------------------------------- sweep

    def _sweep_loop(self):
        """Force a retained-store replay every sweep interval (see module doc:
        without this, a landmine planted while we're connected is invisible)."""
        while not self._stop.wait(config.RETAINED_WATCHDOG_SWEEP_S):
            if not (self.client and self.connected):
                continue
            try:
                for pattern in self._patterns():
                    self.client.unsubscribe(pattern)
                    self.client.subscribe(pattern)
            except Exception:  # noqa: BLE001 - a failed sweep just waits for the next
                logger.exception("Retained watchdog: resubscribe sweep failed")

    # ------------------------------------------------------------------- API

    def start(self):
        self.client = mqtt.Client(
            client_id=f"watchtower_retained_watchdog_{uuid.uuid4().hex[:8]}")
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        # connect_async + loop_start so a broker that isn't up yet (or drops)
        # is retried forever in the background — same rationale as MQTTClient.
        self.client.connect_async(config.MQTT_BROKER, config.MQTT_PORT, 60)
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.loop_start()
        self._sweep_thread = threading.Thread(
            target=self._sweep_loop, name="retained-watchdog-sweep", daemon=True)
        self._sweep_thread.start()
        logger.info(
            f"Retained watchdog started (sweep every {config.RETAINED_WATCHDOG_SWEEP_S}s)")

    def get_stats(self) -> dict:
        with self.lock:
            return {
                "connected": self.connected,
                "sweep_interval_s": config.RETAINED_WATCHDOG_SWEEP_S,
                "watched_suffixes": list(config.RETAINED_WATCHDOG_SUFFIXES),
                "total_erased": sum(self.erase_counts.values()),
                "recent": list(self.erasures),
            }


watchdog = RetainedCommandWatchdog()
