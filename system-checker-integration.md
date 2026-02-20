# WatchTower System Checker Integration Guide

## Overview

**WatchTower** is the centralized hardware monitoring system for Alchemy Escape Rooms. It's a Python Flask web dashboard (1630 lines) running on the network that continuously tracks the health and status of all escape room devices—BAC controllers and ESP32 microcontrollers—reporting which are online, offline, or misconfigured.

### Repository
- **GitHub**: https://github.com/Alchemy-Escape-Rooms-Inc/WatchTower
- **Main file**: `system_checker.py`
- **Configuration**: `config.json`
- **Dashboard**: http://localhost:5000 (when running locally)

---

## Architecture

WatchTower works in three layers:

### 1. **MQTT Subscriber (Message Bus)**
- Connects to Mosquitto MQTT broker at `10.1.10.115:1883`
- Subscribes to device response topics
- Listens for heartbeats and PONG messages from all devices
- Logs all traffic for debugging in the web dashboard

### 2. **Device Status Tracker (Python Flask Backend)**
- Maintains a dictionary of all configured devices
- Assigns each device a **status**: `unknown`, `online`, `offline`, or `testing`
- Measures response time (ms) when devices reply
- Detects timeouts and marks devices offline if they don't respond in time
- Runs a background thread checking timeouts every 500ms

### 3. **Web Dashboard (Flask/HTML/JavaScript)**
- Real-time card-based UI showing device status
- Flip-card interaction to see commands and details
- Live MQTT message log showing all device traffic
- "Test All Devices" button to ping everything at once
- Drag-and-drop reordering of device cards (saved to browser localStorage)
- Auto-refresh every 10 seconds

---

## Device Monitoring Strategy

WatchTower monitors **4 BAC controllers** and **25 ESP32 devices**—but the way it verifies they're alive differs by type:

### BAC Controllers (4 devices)
| Name | Icon | Color | Topic Base |
|------|------|-------|-----------|
| Shattic | S | Blue | `Shattic` |
| Captain | C | Gold | `Captain` |
| Cove | V | Teal | `Cove` |
| Jungle | J | Pink | `Jungle` |

**How BAC monitoring works:**
- BACs send a **heartbeat every 10 seconds** on their `/get/heartbeat` topic
- WatchTower doesn't actively PING BACs (they're not responsive to commands like ESP32s are)
- Instead, it **waits to receive their heartbeat**
- If a heartbeat arrives within ~15 seconds, the BAC is marked **ONLINE**
- If no heartbeat for 15+ seconds, marked **OFFLINE**

### ESP32 Devices (25 total)

| Name | Topic | Needs WatchTower? | Status |
|------|-------|------------------|--------|
| Cannon1 | Cannon1 | No | Ready |
| Cannon2 | Cannon2 | No | Ready |
| RoseCompass | RoseCompass | No | Ready |
| CabinDoor | CabinDoor | No | Ready |
| JungleDoor | JungleDoor | No | Ready |
| Driftwood | Driftwood | No | Ready |
| SeaShells | SeaShells | No | Ready |
| **ShipMotion1** | ShipMotion1 | **Yes** | NOT YET |
| **ShipMotion2** | ShipMotion2 | **Yes** | NOT YET |
| **ShipMotion3** | ShipMotion3 | **Yes** | NOT YET |
| **BarrelPiston** | BarrelPiston | **Yes** | NOT YET |
| **JungleMotion1** | JungleMotion1 | **Yes** | NOT YET |
| **JungleMotion2** | JungleMotion2 | **Yes** | NOT YET |
| **JungleMotion3** | JungleMotion3 | **Yes** | NOT YET |
| **CoveSlidingDoor** | cove_sliding_door | **Yes** | NOT YET |
| **WaterFountain** | WaterFountain | **Yes** | NOT YET |
| **SunDial** | SunDial | **Yes** | NOT YET |
| **RuinsWallPanel** | RuinsWallPanel | **Yes** | NOT YET |
| **Hieroglyphics** | Hieroglyphics | No repo | NOT_INSTALLED |
| **TridentReveal** | TridentReveal | No repo | NOT_INSTALLED |
| **StarCharts** | StarCharts | No repo | NOT_INSTALLED |
| **MonkeyTombEntrance** | MonkeyTombEntrance | No repo | NOT_INSTALLED |
| **TridentCabinet** | TridentCabinet | No repo | NOT_INSTALLED |
| **MagicMirror2** | MagicMirror2 | No repo | NOT_INSTALLED |
| **StarTable** | StarTable | No repo | NOT_INSTALLED |
| **TridentAltar** | TridentAltar | No repo | NOT_INSTALLED |

**How ESP32 monitoring works:**
- WatchTower sends a **PING** command on `MermaidsTale/{topic_base}/command`
- ESP32 firmware must respond with **PONG** on `MermaidsTale/{topic_base}/command`
- Timeout is **3 seconds** for ESP32 (they're fast)
- If PONG arrives in time, marked **ONLINE**
- If no response, marked **OFFLINE**

---

## The "needs_protocol" Flag

Many ESP32 devices in config.json have `"needs_protocol": true`. This means:

**The device is physically installed and connected to the network, BUT its firmware doesn't yet implement the WatchTower protocol (PING/PONG).**

What this means for operations:
- The device **won't respond** to WatchTower's PING commands
- It will show as **OFFLINE** or **UNKNOWN** in the dashboard (orange "NEEDS UPDATE" badge)
- The hardware is there and working—the code just doesn't have PING/PONG support yet
- **Before pre-game checklist**: firmware on these devices must be updated to support PING/PONG

### Devices marked "needs_protocol: true" (11 total)
- ShipMotion1, ShipMotion2, ShipMotion3
- BarrelPiston
- JungleMotion1, JungleMotion2, JungleMotion3
- CoveSlidingDoor
- WaterFountain
- SunDial
- RuinsWallPanel

### Devices marked "NOT_INSTALLED" (no GitHub repo, empty firmware code)
These are reserved in config but have no implementation yet:
- Hieroglyphics
- TridentReveal
- StarCharts
- MonkeyTombEntrance
- TridentCabinet
- MagicMirror2
- StarTable
- TridentAltar

---

## Known Bugs and Quirks

### 1. **False Positives for Offline Devices**
- **Issue**: WatchTower sometimes marks a device offline if a single PING gets lost (network hiccup)
- **Workaround**: Click the device card to re-ping it individually, or click "Test All Devices"
- **Better fix needed**: Implement retry logic—PING 3 times before marking offline

### 2. **Port Mismatch in Config**
- The config.json specifies `"broker_port": 1883`
- But some devices have been tested on port `1883` and port `8883` (MQTT with TLS)
- **Verify on startup**: Dashboard displays current broker connection status at top right
- **If connection fails**: Check that Mosquitto is listening on the configured port and IP

### 3. **BAC Heartbeat Timing**
- BAC heartbeats should arrive every 10 seconds
- If a BAC is slow to respond, the timeout waits 15 seconds (safety margin)
- If a BAC restarts mid-test, it may take 10-15 seconds to detect it's back online

### 4. **MQTT Message Flooding**
- When testing many devices, the message log fills up fast
- Old messages are automatically pruned (max 100 messages kept)
- Use the "Clear" button in MQTT panel to see traffic more clearly

---

## Adding New Devices to WatchTower

When you add a new ESP32 prop to the escape room:

### Step 1: Add to config.json
```json
{
    "name": "MyNewProp",
    "topic": "MyNewProp",
    "icon": "MN",
    "color": "#4A90D9",
    "commands": ["PING", "STATUS", "RESET", "PUZZLE_RESET"]
}
```

### Step 2: Configure the fields
- **name**: Display name on dashboard (what users see)
- **topic**: MQTT topic base (e.g., `MermaidsTale/MyNewProp/command`)
- **icon**: 1-2 char abbreviation for card display
- **color**: Hex color for card styling
- **commands**: List of commands this device supports (optional, defaults shown above)

### Step 3: If using WatchTower protocol
- Firmware must respond to PING on `MermaidsTale/{topic}/command` with PONG
- Leave `"needs_protocol": false` (default)
- Or add `"needs_protocol": true` while firmware is being developed

### Step 4: Restart WatchTower
```bash
# If running as daemon
systemctl restart watchtower

# Or manually
python system_checker.py
```

---

## Recommended Improvements

### Priority 1: Better False Positive Handling
- Implement retry logic: PING 3 times before marking offline
- Only mark offline if all 3 fail
- Reduces spurious "OFFLINE" alerts from network glitches

### Priority 2: Timeout Configuration
- Move timeout values to config.json instead of hardcoded in Python
- Allow different timeouts per device
- Example: `"ping_timeout_ms": 3000`

### Priority 3: Device Grouping by Room
- Organize devices by escape room location (Ship, Jungle, Cove, etc.)
- Dashboard sections: "Ship Area", "Jungle Area", etc.
- Makes pre-game checks faster (check Ship, then check Cove, etc.)

### Priority 4: Firmware Version Tracking
- Each device reports its firmware version in STATUS response
- WatchTower tracks and displays firmware versions
- Alerts if device firmware is out of date

---

## Pre-Game Checklist Script Proposal

Before every game session, operations should run automated checks. Here's what should happen:

### Checklist: Run Before Every Game

```
[ ] Step 1: Verify Mosquitto broker is running
    Command: systemctl status mosquitto
    Expected: "active (running)"
    If failed: systemctl start mosquitto

[ ] Step 2: PING all WatchTower-compliant devices
    - Open WatchTower dashboard: http://localhost:5000
    - Click "Test All Devices"
    - Wait 5 seconds for responses
    - All devices should show GREEN status

    Devices that should respond (9 total):
    - BACs: Shattic, Captain, Cove, Jungle
    - ESP32s: Cannon1, Cannon2, RoseCompass, CabinDoor, JungleDoor, Driftwood, SeaShells

    If any RED (OFFLINE):
    - Click the card to re-test individually
    - Check device network connectivity
    - Restart device if unresponsive
    - Do NOT start game if any device is offline

[ ] Step 3: Check BAC heartbeats
    - In WatchTower MQTT panel, look for messages with "/get/heartbeat"
    - Should see one heartbeat per BAC every 10 seconds
    - Watch for 15 seconds
    - If no heartbeat from a BAC: the BAC is dead or disconnected
    - Do NOT start game if any BAC is missing heartbeats

[ ] Step 4: Report device status
    - Screenshot or note the status bar counts
    - Example: "4 online, 0 offline, 0 unknown"
    - Write to operations log

[ ] Step 5: Flag devices with wrong firmware
    - Devices marked ORANGE ("NEEDS UPDATE"):
      ShipMotion1, ShipMotion2, ShipMotion3
      BarrelPiston, JungleMotion1, JungleMotion2, JungleMotion3
      CoveSlidingDoor, WaterFountain, SunDial, RuinsWallPanel
    - These devices exist but don't support WatchTower protocol yet
    - Mark in checklist: "Firmware update pending"
    - Once firmware is updated, they'll respond to PING

[ ] Step 6: Verify M3 (Game Master Controller) can publish to all prop topics
    - Open terminal
    - Command: mosquitto_pub -h 10.1.10.115 -t MermaidsTale/Cannon1/command -m "PING"
    - Check WatchTower dashboard: Cannon1 should show "Testing..." briefly then "Online"
    - Repeat for 3 random devices
    - If any fail: M3 network is broken or broker not responding
```

### Implementation Notes
- Store checklist as a bash script that outputs results
- Logs results to `/var/log/alchemy-checklist-{timestamp}.log`
- Exits with status 0 if all checks pass, 1 if any critical device is down
- Can be run via cron before scheduled game slots

---

## Quick Reference: Device Status Meanings

| Status | Icon | What It Means | Action |
|--------|------|---------------|--------|
| **ONLINE** | Green | Device responded to PING or sent heartbeat | Ready to use |
| **OFFLINE** | Red | Device didn't respond in time | Check power, network, restart device |
| **UNKNOWN** | Gray | Never been tested yet | Click card to test |
| **TESTING** | Blue + pulsing | Currently sending PING, waiting for response | Wait for result |
| **NEEDS UPDATE** | Orange badge | Device exists but firmware doesn't support PING/PONG | Update firmware, then test |
| **NOT_INSTALLED** | Grayed out | Device is in config but has no GitHub repo/code | Hardware not built yet |

---

## Troubleshooting

### "Broker Disconnected" in dashboard
- **Cause**: WatchTower can't reach Mosquitto at 10.1.10.115:1883
- **Fix**:
  - Check Mosquitto is running: `systemctl status mosquitto`
  - Check IP is correct: `ping 10.1.10.115`
  - Check port: `sudo netstat -tulpn | grep 1883`

### All devices show OFFLINE
- **Cause 1**: MQTT broker down
- **Cause 2**: Network unreachable
- **Fix**: Restart mosquitto, check network cables

### One device stuck on OFFLINE
- **Cause**: Device crashed, lost power, or network disconnected
- **Fix**:
  - Check device has power
  - Check network cable or WiFi connection
  - Restart device
  - Re-test by clicking card

### Message log not updating
- **Cause**: MQTT subscription failed or no traffic
- **Fix**:
  - Verify broker is connected (check badge at top)
  - Manually send a test message: `mosquitto_pub -h 10.1.10.115 -t test -m "hello"`
  - Should appear in log within 1 second

---

## System Resources

- **Python Version**: 3.7+
- **Memory**: ~50 MB (Flask app + MQTT client)
- **Network**: 1 Mbps average (light traffic)
- **CPU**: <2% idle, spikes to 5% during full device test
- **Disk**: Minimal (no database, just in-memory state)

The system is designed to run 24/7 with minimal overhead.
