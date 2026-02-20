"""
WatchTower V2 API Routes
==========================
REST endpoints for the frontend to consume.
"""

import json
import requests
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request

import config
from models import database as db

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")

# MQTT client reference - set by app.py on startup
mqtt_client = None


def set_mqtt_client(client):
    global mqtt_client
    mqtt_client = client


# =============================================================================
# DEVICE STATUS
# =============================================================================

@api.route("/status")
def get_status():
    if mqtt_client:
        return jsonify(mqtt_client.get_status_summary())
    return jsonify({"error": "MQTT client not initialized"}), 500


@api.route("/ping/<device_name>")
def ping_device(device_name):
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    result = mqtt_client.ping_device(device_name)
    return jsonify({"device": device_name, "ping_sent": result})


@api.route("/ping-all")
def ping_all():
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    mqtt_client.ping_all()
    return jsonify({"status": "pinging all devices"})


@api.route("/command/<device_name>/<command>")
def send_command(device_name, command):
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    result = mqtt_client.send_command(device_name, command)
    return jsonify(result)


# =============================================================================
# MQTT FEED
# =============================================================================

@api.route("/messages")
def get_messages():
    if not mqtt_client:
        return jsonify({"error": "MQTT client not initialized"}), 500
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"messages": mqtt_client.get_feed(limit)})


# =============================================================================
# DEBUG LOG
# =============================================================================

@api.route("/debug-log", methods=["GET"])
def get_debug_log():
    device = request.args.get("device")
    resolved = request.args.get("resolved")
    if resolved is not None:
        resolved = resolved.lower() == "true"
    entries = db.get_debug_entries(device_name=device, resolved=resolved)
    return jsonify({"entries": entries})


@api.route("/debug-log", methods=["POST"])
def add_debug_log():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    entry_id = db.add_debug_entry(
        device_name=data.get("device_name"),
        severity=data.get("severity", "info"),
        title=data["title"],
        description=data.get("description"),
        resolution=data.get("resolution"),
        created_by=data.get("created_by", "manual")
    )
    return jsonify({"id": entry_id, "status": "created"})


@api.route("/debug-log/<int:entry_id>/resolve", methods=["POST"])
def resolve_debug_log(entry_id):
    data = request.get_json() or {}
    db.resolve_debug_entry(entry_id, data.get("resolution"))
    return jsonify({"status": "resolved"})


# =============================================================================
# TODO / CLICKUP INTEGRATION
# =============================================================================

@api.route("/todos", methods=["GET"])
def get_todos():
    device = request.args.get("device")
    status = request.args.get("status")
    todos = db.get_todos(device_name=device, status=status)
    return jsonify({"todos": todos})


@api.route("/todos", methods=["POST"])
def create_todo():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    # Create in ClickUp first
    clickup_result = _create_clickup_task(data)

    # Create locally
    todo_id = db.add_todo(
        title=data["title"],
        device_name=data.get("device_name"),
        description=data.get("description"),
        priority=data.get("priority", "normal"),
        due_date=data.get("due_date"),
        assigned_to=data.get("assigned_to"),
        clickup_task_id=clickup_result.get("id"),
        clickup_task_url=clickup_result.get("url")
    )

    return jsonify({
        "id": todo_id,
        "clickup_task_id": clickup_result.get("id"),
        "clickup_url": clickup_result.get("url"),
        "status": "created"
    })


@api.route("/todos/<int:todo_id>/status", methods=["POST"])
def update_todo_status(todo_id):
    data = request.get_json() or {}
    new_status = data.get("status", "done")
    db.update_todo_status(todo_id, new_status)
    return jsonify({"status": "updated"})


# =============================================================================
# MANIFEST / GRIMOIRE
# =============================================================================

@api.route("/manifests")
def get_manifests():
    manifests = db.get_all_manifests()
    return jsonify({"manifests": manifests})


@api.route("/manifests/<device_name>")
def get_manifest(device_name):
    manifest = db.get_manifest(device_name)
    if manifest:
        return jsonify(manifest)
    return jsonify({"error": f"No manifest for {device_name}"}), 404


# =============================================================================
# WORKSPACE INFO
# =============================================================================

@api.route("/workspace/members")
def get_workspace_members():
    """Get ClickUp workspace members for assignment dropdown."""
    try:
        headers = {"Authorization": config.CLICKUP_API_TOKEN}
        resp = requests.get(
            f"{config.CLICKUP_API_URL}/team/{config.CLICKUP_WORKSPACE_ID}/member",
            headers=headers,
            timeout=5
        )
        if resp.status_code == 200:
            return jsonify(resp.json())
    except Exception as e:
        logger.error(f"Failed to get ClickUp members: {e}")

    return jsonify({"members": []})


@api.route("/gravity-games/topics")
def get_gravity_games_topics():
    """Return the full Gravity Games MQTT topic table."""
    return jsonify({"topics": config.GRAVITY_GAMES_TOPICS})


# =============================================================================
# CLICKUP HELPER
# =============================================================================

def _create_clickup_task(data: dict) -> dict:
    """Create a task in ClickUp's WatchTower Issues list."""
    if not config.CLICKUP_API_TOKEN:
        logger.warning("No ClickUp API token configured - skipping ClickUp task creation")
        return {}

    try:
        # Map priority names to ClickUp values
        priority_map = {"urgent": 1, "high": 2, "normal": 3, "low": 4}

        task_data = {
            "name": data["title"],
            "description": data.get("description", ""),
            "priority": priority_map.get(data.get("priority", "normal"), 3),
        }

        # Add device tag
        if data.get("device_name"):
            task_data["tags"] = [data["device_name"]]
            task_data["description"] = f"**Device:** {data['device_name']}\n\n{task_data['description']}"

        # Add due date (ClickUp wants Unix ms)
        if data.get("due_date"):
            try:
                dt = datetime.strptime(data["due_date"], "%Y-%m-%d")
                task_data["due_date"] = int(dt.timestamp() * 1000)
            except ValueError:
                pass

        headers = {
            "Authorization": config.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }

        resp = requests.post(
            f"{config.CLICKUP_API_URL}/list/{config.CLICKUP_LIST_ID}/task",
            headers=headers,
            json=task_data,
            timeout=10
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            logger.info(f"Created ClickUp task: {result.get('id')} - {data['title']}")
            return {"id": result.get("id"), "url": result.get("url")}
        else:
            logger.error(f"ClickUp API error {resp.status_code}: {resp.text}")
            return {}

    except Exception as e:
        logger.error(f"Failed to create ClickUp task: {e}")
        return {}
