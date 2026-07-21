"""
One-shot MQTT discovery snapshot.
Connects to the live broker, subscribes to '#', captures every topic seen
(retained + live) for a fixed window, and prints a sorted summary so we can
reconcile the WatchTower registry against ground truth.
"""
import sys
import time
import collections
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"   # broker only answers on loopback from this host; ESP devices hit 10.1.10.115 over LAN
PORT = 1883
WINDOW = 25  # seconds

topics = collections.OrderedDict()   # topic -> last payload (truncated)
counts = collections.Counter()
roots = collections.Counter()
connected = {"ok": False, "err": None}


def on_connect(client, userdata, flags, rc, *a):
    if rc == 0:
        connected["ok"] = True
        client.subscribe("#", qos=0)
    else:
        connected["err"] = f"rc={rc}"


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", "replace")[:80]
    topics[msg.topic] = payload
    counts[msg.topic] += 1
    roots[msg.topic.split("/")[0]] += 1


client = mqtt.Client(client_id="watchtower-snapshot")
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(BROKER, PORT, keepalive=30)
except Exception as e:
    print(f"CONNECT_FAILED: {e}")
    sys.exit(2)

client.loop_start()
deadline = time.time() + WINDOW
while time.time() < deadline:
    time.sleep(0.5)
client.loop_stop()
client.disconnect()

if not connected["ok"]:
    print(f"NOT_CONNECTED: {connected['err']}")
    sys.exit(3)

print(f"=== SNAPSHOT: {len(topics)} unique topics over {WINDOW}s ===\n")
print("--- TOP-LEVEL ROOTS ---")
for root, n in roots.most_common():
    print(f"  {root:30s} {n:6d} msgs")

print("\n--- ALL TOPICS (topic | count | last payload) ---")
for t in sorted(topics):
    print(f"  {t:55s} {counts[t]:5d}  {topics[t]!r}")
