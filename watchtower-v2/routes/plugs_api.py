"""
WatchTower V2 — Smart Plug API
================================
REST endpoints behind the Power page. All the heavy lifting lives in
alexa_plugs.AlexaPlugsManager; these routes just bridge Flask <-> its loop.
"""

import logging

from flask import Blueprint, jsonify, request

from alexa_plugs import manager

logger = logging.getLogger(__name__)

plugs_api = Blueprint("plugs_api", __name__, url_prefix="/api/plugs")


@plugs_api.route("", methods=["GET"])
def plugs_status():
    return jsonify(manager.status())


@plugs_api.route("/login", methods=["POST"])
def plugs_login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    if not email:
        return jsonify({"error": "Amazon account email required"}), 400
    # The proxy URL must be reachable from the operator's browser, so build it
    # from whatever host they used to reach WatchTower (localhost or LAN IP).
    host = request.host.split(":")[0]
    try:
        url = manager.begin_login(email, host, body.get("otp_secret", ""))
        return jsonify({"login_url": url, "otp_code": manager.otp_code()})
    except Exception as e:  # noqa: BLE001
        logger.exception("plug login start failed")
        return jsonify({"error": str(e)}), 500


@plugs_api.route("/otp", methods=["GET"])
def plugs_otp():
    return jsonify({"code": manager.otp_code()})


@plugs_api.route("/refresh", methods=["POST"])
def plugs_refresh():
    try:
        return jsonify({"devices": manager.refresh()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@plugs_api.route("/states", methods=["GET"])
def plugs_states():
    try:
        return jsonify({"devices": manager.poll_states()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@plugs_api.route("/power", methods=["POST"])
def plugs_power():
    body = request.get_json(silent=True) or {}
    entity_id = body.get("entity_id")
    on = body.get("on")
    if not entity_id or on is None:
        return jsonify({"error": "entity_id and on required"}), 400
    try:
        manager.set_power(entity_id, bool(on))
        return jsonify({"ok": True})
    except Exception as e:  # noqa: BLE001
        logger.exception("plug power failed")
        return jsonify({"error": str(e)}), 500


@plugs_api.route("/all", methods=["POST"])
def plugs_all():
    body = request.get_json(silent=True) or {}
    on = body.get("on")
    if on is None:
        return jsonify({"error": "on required"}), 400
    try:
        manager.set_all(bool(on))
        return jsonify({"ok": True})
    except Exception as e:  # noqa: BLE001
        logger.exception("plug all failed")
        return jsonify({"error": str(e)}), 500
