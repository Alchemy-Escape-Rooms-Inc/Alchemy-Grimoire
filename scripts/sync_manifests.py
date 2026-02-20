"""
Manifest Sync — WatchTower V2
==============================
Reads MANIFEST.h files from device repos on disk and syncs their
data into the WatchTower SQLite database.

Usage:
    python scripts/sync_manifests.py                    # scan all repos
    python scripts/sync_manifests.py --repo /path/to    # single repo
    python scripts/sync_manifests.py --dry-run          # preview only
    python scripts/sync_manifests.py --list             # show found repos

The script scans REPO_BASE_DIR for any folder containing a MANIFEST.h,
parses the #define values, and calls db.upsert_manifest().

MANIFEST.h expected format (any subset of fields is OK):
    #define DEVICE_NAME        "JungleDoor"
    #define FIRMWARE_VERSION   "v2.1.0"
    #define BOARD_TYPE         "ESP32-S3"
    #define ROOM               "Jungle"
    #define DESCRIPTION        "Motorized sliding door..."
    #define BUILD_STATUS       "compiles"
    #define CODE_HEALTH        "good"
    #define BROKER_IP          "10.1.10.115"
    #define BROKER_PORT        1883
    #define HEARTBEAT_MS       300000
    #define REPO_URL           "https://github.com/AlchemyEscapeRooms/JungleDoor"
    #define KNOWN_QUIRKS       "PWM on pin 5 needs pull-down"
    #define SUBSCRIBE_TOPICS   "MermaidsTale/JungleDoor/command"
    #define PUBLISH_TOPICS     "MermaidsTale/JungleDoor/status,MermaidsTale/JungleDoor/heartbeat"
    #define SUPPORTED_COMMANDS "open,close,stop,reset,ping,status"
    #define PIN_CONFIG         "PWM=5,DIR=4,LIMIT_OPEN=34,LIMIT_CLOSE=35"
    #define COMPONENTS         "A4988,VNH5019"
    #define WATCHTOWER_COMPLIANCE "full"
"""

import sys
import os
import re
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from models import database as db

# =============================================================================
# CONFIGURATION — adjust REPO_BASE_DIR for your M3 setup
# =============================================================================

# Default repo root on M3 — override with --base or REPO_BASE_DIR env var
REPO_BASE_DIR = os.environ.get(
    "REPO_BASE_DIR",
    os.path.expanduser("~/escape-room-repos")   # adjust to your actual path
)

# Fields in MANIFEST.h and their DB column names
FIELD_MAP = {
    "DEVICE_NAME":            "device_name",
    "FIRMWARE_VERSION":       "firmware_version",
    "BOARD_TYPE":             "board_type",
    "ROOM":                   "room",
    "DESCRIPTION":            "description",
    "BUILD_STATUS":           "build_status",
    "CODE_HEALTH":            "code_health",
    "WATCHTOWER_COMPLIANCE":  "watchtower_compliance",
    "BROKER_IP":              "broker_ip",
    "BROKER_PORT":            "broker_port",
    "HEARTBEAT_MS":           "heartbeat_ms",
    "SUBSCRIBE_TOPICS":       "subscribe_topics",
    "PUBLISH_TOPICS":         "publish_topics",
    "SUPPORTED_COMMANDS":     "supported_commands",
    "PIN_CONFIG":             "pin_config",
    "COMPONENTS":             "components",
    "KNOWN_QUIRKS":           "known_quirks",
    "REPO_URL":               "repo_url",
}

INT_FIELDS = {"broker_port", "heartbeat_ms"}


def find_manifests(base_dir: str) -> list[str]:
    """Walk base_dir and return paths to all MANIFEST.h files found."""
    found = []
    if not os.path.isdir(base_dir):
        return found
    for root, dirs, files in os.walk(base_dir):
        # Skip .git and build directories
        dirs[:] = [d for d in dirs if d not in {".git", "build", ".pio", "node_modules"}]
        for fname in files:
            if fname == "MANIFEST.h":
                found.append(os.path.join(root, fname))
    return found


def parse_manifest(path: str) -> dict | None:
    """
    Parse a MANIFEST.h file and return a dict of DB fields.
    Returns None if DEVICE_NAME is not found.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError as e:
        print(f"  ⚠️  Cannot read {path}: {e}")
        return None

    data = {}

    for macro, column in FIELD_MAP.items():
        # Match:  #define MACRO_NAME   "value"   or   #define MACRO_NAME   123
        pattern = rf'#\s*define\s+{re.escape(macro)}\s+"([^"]*)"'
        m = re.search(pattern, raw)
        if m:
            val = m.group(1).strip()
            data[column] = int(val) if column in INT_FIELDS and val.isdigit() else val
            continue

        # Try unquoted integer
        pattern_int = rf'#\s*define\s+{re.escape(macro)}\s+(\d+)'
        m = re.search(pattern_int, raw)
        if m:
            data[column] = int(m.group(1)) if column in INT_FIELDS else m.group(1)

    if "device_name" not in data:
        print(f"  ⚠️  No DEVICE_NAME in {path} — skipping")
        return None

    data["raw_manifest"] = raw[:4000]  # store truncated raw text
    return data


def sync_manifest(manifest_data: dict, dry_run: bool = False) -> bool:
    name = manifest_data["device_name"]
    if dry_run:
        print(f"  [DRY RUN] Would sync: {name}")
        for k, v in manifest_data.items():
            if k != "raw_manifest":
                print(f"    {k:<28} = {str(v)[:60]}")
        return True
    try:
        db.upsert_manifest(name, manifest_data)
        return True
    except Exception as e:
        print(f"  ❌ DB error for {name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Sync MANIFEST.h files to WatchTower DB")
    parser.add_argument("--base", help="Override repo base directory", default=REPO_BASE_DIR)
    parser.add_argument("--repo", help="Sync a single specific repo directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--list", action="store_true", help="List found MANIFEST.h files and exit")
    args = parser.parse_args()

    db.init_db(config.DATABASE_PATH)

    print()
    print("=" * 62)
    print("  🔄 WatchTower Manifest Sync")
    print("=" * 62)

    if args.dry_run:
        print("  🔍 DRY RUN — no DB writes\n")

    base = args.base
    if args.repo:
        manifests = []
        candidate = os.path.join(args.repo, "MANIFEST.h")
        if os.path.exists(candidate):
            manifests = [candidate]
        else:
            # Search within the given path
            manifests = find_manifests(args.repo)
    else:
        print(f"  Scanning: {base}\n")
        manifests = find_manifests(base)

    if not manifests:
        print(f"  ⚠️  No MANIFEST.h files found under: {base}")
        print()
        print("  Tips:")
        print("  - Set REPO_BASE_DIR env var to your repo root")
        print("  - Or use --base /path/to/repos")
        print("  - Or use --repo /path/to/specific-repo")
        print()
        return

    if args.list:
        print(f"  Found {len(manifests)} MANIFEST.h file(s):\n")
        for m in manifests:
            print(f"  {m}")
        print()
        return

    print(f"  Found {len(manifests)} manifest(s)\n")

    synced = 0
    failed = 0

    for manifest_path in manifests:
        repo_name = os.path.basename(os.path.dirname(manifest_path))
        print(f"  📄 {repo_name}")
        print(f"     {manifest_path}")

        data = parse_manifest(manifest_path)
        if data is None:
            failed += 1
            continue

        print(f"     Device: {data['device_name']} | "
              f"FW: {data.get('firmware_version', '?')} | "
              f"Board: {data.get('board_type', '?')}")

        if sync_manifest(data, dry_run=args.dry_run):
            print(f"     {'[DRY RUN]' if args.dry_run else '✅'} Synced")
            synced += 1
        else:
            failed += 1
        print()

    print("─" * 62)
    print(f"  {'Would sync' if args.dry_run else 'Synced'}: {synced}  |  Failed: {failed}")
    print()

    if synced > 0 and not args.dry_run:
        print("  ✅ Manifest data is now live in WatchTower.")
        print("  📋 View at: http://10.1.10.115:5000/library → Device Manifests")
    print()


if __name__ == "__main__":
    main()
