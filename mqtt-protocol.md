# Alchemy Escape Rooms — MQTT Protocol Standard

This document is the **authoritative standard** for MQTT communication across all ESP32 devices in "A Mermaid's Tale." Every device connected to WatchTower must conform to this protocol.

> **Source of truth:** Extracted from `alchemy-project-documentation.md` (Section 9) and promoted to a standalone standard document.

---

## Broker & Network

| Setting | Value |
|---|---|
| **Broker IP** | `10.1.10.115` |
| **Broker Port** | `1883` |
| **WiFi SSID** | `AlchemyGuest` |
| **WiFi Password** | `VoodooVacation5601` |
| **Topic Pattern** | `MermaidsTale/{DeviceName}/{suffix}` |

---

## Standard Topic Suffixes

| Suffix | Direction | Purpose |
|---|---|---|
| `/command` | Subscribe | Receive commands from WatchTower/game controller |
| `/status` | Publish | State changes, heartbeat messages |
| `/log` | Publish | Mirrored serial output for remote debugging |
| `/limit` | Publish | Limit switch events (door controllers only) |

---

## Required Commands (WatchTower Protocol)

Every WatchTower-compliant device must support all four of these commands:

| Command | Response | Description |
|---|---|---|
| `PING` | `PONG` | Health check — System Checker sends this periodically |
| `STATUS` | State string with diagnostics | Full status report (state, uptime, RSSI, version, etc.) |
| `RESET` | `OK` then reboot | Software reboot — stops all actuators first |
| `PUZZLE_RESET` | `OK` | Reset game state without rebooting — re-read sensors, sync state |

---

## Standard Boot Sequence

Every device must follow this sequence on power-on or reboot:

1. Initialize hardware (pins, sensors, motors)
2. Connect to WiFi (`AlchemyGuest`)
3. Connect to MQTT broker (`10.1.10.115:1883`)
4. Subscribe to `MermaidsTale/{DeviceName}/command`
5. Publish `ONLINE` on `/status`
6. Begin heartbeat loop

---

## Heartbeat Standard

- **Interval:** `300000` ms (5 minutes) — this is the WatchTower standard
- **Format:** `HEARTBEAT:{state}:UP{uptime}s:RSSI{signal}`
- **Topic:** `/status`

> ⚠️ Some older devices (JungleDoor, CoveDoor) use 30-second heartbeats. This is non-standard and creates unnecessary MQTT traffic. New devices must use 5 minutes.

---

## Device Naming Convention

- PascalCase, no spaces, no special characters
- Examples: `Cannon1`, `JungleDoor`, `CoveDoor`, `BarrelPiston`, `ShipMotion1`
- The device name must be **identical** across: firmware code, MQTT topics, WatchTower config, and Grimoire registry
- A space in a device name (e.g., `Jungle Door`) creates a broken MQTT topic and the device will never receive commands

---

## PONG Response Topic

The standard is to publish `PONG` on the **same topic the command was received on** (`/command`). WatchTower listens on both `/command` and `/status` as a workaround for legacy devices, but all new devices must PONG on `/command`.

---

*For the cross-device issues and known deviations from this standard, see [`quirks-registry.md`](quirks-registry.md).*  
*For how these values are declared in firmware, see [`manifest-protocol.md`](manifest-protocol.md).*
