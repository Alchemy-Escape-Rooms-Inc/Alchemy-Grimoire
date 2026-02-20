"""
WatchTower V2 Configuration
============================
All settings for MQTT, ClickUp, database, and device registry.
"""

import os

# =============================================================================
# NETWORK
# =============================================================================
MQTT_BROKER = "10.1.10.115"
MQTT_PORT = 1883
WIFI_SSID = "AlchemyGuest"
WIFI_PASSWORD = "VoodooVacation5601"

# =============================================================================
# FLASK
# =============================================================================
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
SECRET_KEY = os.urandom(24).hex()

# =============================================================================
# DATABASE
# =============================================================================
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "watchtower.db")

# =============================================================================
# CLICKUP
# =============================================================================
CLICKUP_API_TOKEN = os.environ.get("CLICKUP_API_TOKEN", "pk_114238061_3PZ4VQGN7J6D853HXZDYYH9QUMX5GJUD")
CLICKUP_WORKSPACE_ID = "9011667818"
CLICKUP_LIST_ID = "901113164349"  # WatchTower Issues list
CLICKUP_API_URL = "https://api.clickup.com/api/v2"

# =============================================================================
# DEVICE TIMEOUTS
# =============================================================================
ESP32_PING_TIMEOUT = 3.0   # seconds
BAC_PING_TIMEOUT = 15.0    # seconds (waits for heartbeat cycle)
HEARTBEAT_STANDARD = 300000  # 5 minutes in ms

# =============================================================================
# MQTT MESSAGE FILTERING
# =============================================================================
DELTA_THRESHOLD = 2  # degrees - only show sensor changes greater than this
DELTA_TOPICS = ["/Hor", "/Ver", "/angle", "/distance"]
HIDDEN_TOPICS = ["/heartbeat", "/get/heartbeat"]
DEDUP_TOPICS = ["/Loaded", "/Fired", "/triggered"]
MAX_MESSAGES = 200

# =============================================================================
# DEVICE REGISTRY
# =============================================================================
# Device type constants
DEVICE_TYPE_ESP32 = "esp32"
DEVICE_TYPE_BAC = "bac"

# BAC Controllers
BAC_CONTROLLERS = [
    {"name": "Shattic", "icon": "🚢", "color": "#4A90D9"},
    {"name": "Captain", "icon": "🎖️", "color": "#C4A265"},
    {"name": "Cove", "icon": "🏝️", "color": "#45B7AA"},
    {"name": "Jungle", "icon": "🌴", "color": "#7B68D9"},
]

# ESP32 Devices - organized by room
ESP32_DEVICES = [
    # Captain's Cabin
    {"name": "DeskDrawer", "topic": "DeskDrawer", "icon": "🗄️", "color": "#C4A265", "room": "Captain's Cabin"},
    {"name": "MirrorSensor", "topic": "MirrorSensor", "icon": "🪞", "color": "#C4A265", "room": "Captain's Cabin"},
    {"name": "Captains-Cuffs", "topic": "CaptainsCuffs", "icon": "⛓️", "color": "#C4A265", "room": "Captain's Cabin"},
    {"name": "CabinDoor", "topic": "CabinDoor", "icon": "🚪", "color": "#C4A265", "room": "Captain's Cabin"},

    # Ship Deck / Shattic
    {"name": "ShipMotion1", "topic": "ShipMotion1", "icon": "🚢", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "ShipMotion2", "topic": "ShipMotion2", "icon": "🚢", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "ShipMotion3", "topic": "ShipMotion3", "icon": "🚢", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "PirateWheel", "topic": "PirateWheel", "icon": "☸️", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Compass", "topic": "Compass", "icon": "🧭", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "ShipNavMap", "topic": "ShipNavMap", "icon": "🗺️", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Cannon1", "topic": "Cannon1", "icon": "💣", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Cannon2", "topic": "Cannon2", "icon": "💣", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "BarrelPiston", "topic": "BarrelPiston", "icon": "🛢️", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Balancing-Scale", "topic": "BalancingScale", "icon": "⚖️", "color": "#4A90D9", "room": "Ship Deck"},
    {"name": "Sun-Dial", "topic": "SunDial", "icon": "☀️", "color": "#4A90D9", "room": "Ship Deck"},

    # Jungle
    {"name": "JungleDoor", "topic": "JungleDoor", "icon": "🚪", "color": "#45B7AA", "room": "Jungle"},
    {"name": "JungleMotion1", "topic": "JungleMotion1", "icon": "🌿", "color": "#45B7AA", "room": "Jungle"},
    {"name": "JungleMotion2", "topic": "JungleMotion2", "icon": "🌿", "color": "#45B7AA", "room": "Jungle"},
    {"name": "JungleMotion3", "topic": "JungleMotion3", "icon": "🌿", "color": "#45B7AA", "room": "Jungle"},
    {"name": "Driftwood", "topic": "Driftwood", "icon": "🪵", "color": "#45B7AA", "room": "Jungle"},
    {"name": "WaterFountain", "topic": "WaterFountain", "icon": "⛲", "color": "#45B7AA", "room": "Jungle"},
    {"name": "Hieroglyphics", "topic": "Hieroglyphics", "icon": "📜", "color": "#7B68D9", "room": "Jungle"},
    {"name": "TridentReveal", "topic": "TridentReveal", "icon": "🔱", "color": "#7B68D9", "room": "Jungle"},
    {"name": "Ruins-Wall-Panel", "topic": "RuinsWallPanel", "icon": "🧱", "color": "#7B68D9", "room": "Jungle"},

    # Cove
    {"name": "CoveDoor", "topic": "CoveDoor", "icon": "🚪", "color": "#D97B9F", "room": "Cove"},
    {"name": "SeaShells", "topic": "SeaShells", "icon": "🐚", "color": "#D97B9F", "room": "Cove"},
    {"name": "StarCharts", "topic": "StarCharts", "icon": "⭐", "color": "#D97B9F", "room": "Cove"},
    {"name": "LuminousShell", "topic": "LuminousShell", "icon": "✨", "color": "#D97B9F", "room": "Cove"},
]


# =============================================================================
# GRIMOIRE SLUG MAP
# Maps config device names → grimoire device page slugs
# Multiple devices can share a slug (e.g. Cannon1+Cannon2 → new-cannons)
# =============================================================================
GRIMOIRE_SLUG_MAP = {
    # Ship Deck
    "Cannon1":           "new-cannons",
    "Cannon2":           "new-cannons",
    "ShipMotion1":       "wireless-motion-sensor",
    "ShipMotion2":       "wireless-motion-sensor",
    "ShipMotion3":       "wireless-motion-sensor",
    "BarrelPiston":      "barrel-piston",
    "ShipNavMap":        "ship-nav-map",
    "Balancing-Scale":   "balancing-scale",
    "Sun-Dial":          "sun-dial",
    # Captain's Cabin
    "Compass":           "compass",
    "Captains-Cuffs":    "captains-cuffs",
    "CabinDoor":         "cabin-door",
    "StarCharts":        "star-charts",
    # Cove
    "CoveDoor":          "cove-sliding-door",
    "Driftwood":         "driftwood",
    "SeaShells":         "luminous-shell",
    "LuminousShell":     "luminous-shell",
    # Jungle
    "JungleDoor":        "jungle-door",
    "Hieroglyphics":     "ruins-wall-panel",
    "Ruins-Wall-Panel":  "ruins-wall-panel",
    "WaterFountain":     "water-fountain",
}

# Gravity Games VR Topics (game flow triggers, NOT device management)
GRAVITY_GAMES_TOPICS = [
    {"topic": "MermaidsTale/GameRestart", "event": "Game Restart", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/GameStart", "event": "Game Start", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/DeskDrawer", "event": "Desk Drawer", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/MirrorSensor", "event": "Mirror Sensor", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/CabinDoorOpened", "event": "Cabin Door Opened", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/ShipMotion1", "event": "Ship Motion 1", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/ShipMotion2", "event": "Ship Motion 2", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/ShipMotion3", "event": "Ship Motion 3", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/Compasses", "event": "Compasses", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/SkullKeySolved", "event": "Skull Key Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/WheelPos", "event": "Wheel Position", "payload": "pre_n (angle)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon1Hor", "event": "Cannon 1 Aimed", "payload": "pre_n (angle)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon2Hor", "event": "Cannon 2 Aimed", "payload": "pre_n (angle)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon1Loaded", "event": "Cannon 1 Loaded", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon2Loaded", "event": "Cannon 2 Loaded", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon1Fired", "event": "Cannon 1 Fired", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/Cannon2Fired", "event": "Cannon 2 Fired", "payload": "triggered", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/DefenseOver", "event": "Defense Over", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/RumBarrels", "event": "Rum Barrels", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/BalanceScale", "event": "Balancing Scale", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/Swords", "event": "Swords", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/SailUnfurled", "event": "Sail Unfurled", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/SailPosition", "event": "Sail Position", "payload": "pre_n (percent)", "occurrence": "Continuous"},
    {"topic": "MermaidsTale/MapSolved", "event": "Map Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/JungleDoor", "event": "Jungle Door", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/JungleEntered", "event": "Jungle Entered", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/JungleMotion1", "event": "Jungle Motion 1", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/JungleMotion2", "event": "Jungle Motion 2", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/JungleMotion3", "event": "Jungle Motion 3", "payload": "triggered", "occurrence": "Repeat"},
    {"topic": "MermaidsTale/CryptexSolved", "event": "Cryptex Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/WaterfallSolved", "event": "Waterfall Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/DriftwoodSolved", "event": "Driftwood Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/MonkeyGuardianDoor", "event": "Monkey Guardian Door", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/TridentReveal", "event": "Trident Reveal", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/HieroglyphicsSolved", "event": "Hieroglyphics Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/CoveEntered", "event": "Cove Entered", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/SeaShells", "event": "Sea Shells", "payload": "solved", "occurrence": "Once"},
    {"topic": "MermaidsTale/StarCharts", "event": "Star Charts", "payload": "triggered", "occurrence": "Multiple"},
    {"topic": "MermaidsTale/CelestialSolved", "event": "Celestial Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/AlterSolved", "event": "Alter Solved", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/GameSuccess", "event": "Game Success", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/WaterfallFinale", "event": "Waterfall Finale", "payload": "triggered", "occurrence": "Once"},
    {"topic": "MermaidsTale/GameFail", "event": "Game Fail", "payload": "triggered", "occurrence": "Once"},
]
