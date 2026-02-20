# WatchTower V2 — Alchemy Escape Rooms

Integrated monitoring dashboard + Grimoire operations manual + ClickUp task management.

## Quick Start

```bash
cd watchtower-v2
pip install -r requirements.txt
python app.py
```

Dashboard: `http://localhost:5000`

## Setup

### MQTT Broker
Dashboard expects Mosquitto at `10.1.10.115:1883` (configured in `config.py`).
If broker is unreachable, dashboard still works — device status just won't update.

### ClickUp Integration
1. Get a ClickUp Personal API Token from Settings → Apps
2. Set environment variable: `export CLICKUP_API_TOKEN="pk_your_token_here"`
3. Tasks created in the Debug & Tasks tab auto-sync to ClickUp's **WatchTower Issues** list

Without the token, tasks still save locally — they just won't appear in ClickUp.

## Architecture

```
watchtower-v2/
├── app.py              # Flask entry point
├── config.py           # All settings (MQTT, ClickUp, devices, topics)
├── requirements.txt
├── models/
│   └── database.py     # SQLite persistence
├── mqtt/
│   └── __init__.py     # MQTT client, ping/pong, message filtering
├── routes/
│   ├── api.py          # REST endpoints + ClickUp integration
│   └── pages.py        # HTML page routes
├── static/
│   ├── css/style.css   # Alchemy brand theme
│   └── js/app.js       # Shared frontend utilities
└── templates/
    ├── base.html        # Navigation + status bar
    ├── dashboard.html   # Tab 1: Device Registry
    ├── mqtt_feed.html   # Tab 2: MQTT Live Feed
    ├── library.html     # Tab 3: Grimoire Library
    └── debug_log.html   # Tab 4: Debug Log + TODO Tracker
```

## Four Tabs

1. **Device Registry** — 32 devices (28 ESP32 + 4 BAC) organized by room. Click any card for details, commands, manifest data, and issue history.

2. **MQTT Live Feed** — Real-time message viewer with smart filtering (delta suppression, echo suppression, heartbeat hiding). Filter by topic or device name.

3. **Grimoire Library** — Operations manual, wiring reference, network infrastructure, Gravity Games VR topic table (43 topics), and device manifests.

4. **Debug & Tasks** — Log incidents, track resolutions, create tasks that auto-sync to ClickUp with device tags, priority levels, assignees, and due dates.

## ClickUp Integration Details

When you create a task in the Debug & Tasks tab:
- Task is created in ClickUp list `901113164349` (WatchTower Issues)
- Device name is added as a tag (e.g., "JungleDoor")
- Priority maps to ClickUp priority levels (urgent/high/normal/low)
- Due date syncs to ClickUp calendar
- Direct link back to ClickUp task appears in WatchTower

## Devices Monitored

| Room | Count | Examples |
|------|-------|---------|
| BAC Zone Controllers | 4 | Shattic, Captain, Cove, Jungle |
| Captain's Cabin | 4 | DeskDrawer, MirrorSensor, CaptainsCuffs, CabinDoor |
| Ship Deck | 11 | PirateWheel, Compass, Cannon1, Cannon2, BarrelPiston |
| Jungle | 9 | JungleDoor, Driftwood, WaterFountain, Hieroglyphics |
| Cove | 4 | CoveDoor, SeaShells, StarCharts, LuminousShell |
