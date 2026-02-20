#!/usr/bin/env python3
"""
WatchTower V2 — Alchemy Escape Room Monitoring & Operations Dashboard
======================================================================
Integrates device monitoring (WatchTower) with documentation (Grimoire)
and task management (ClickUp) in a single interface.

Author: Built for Alchemy Escape Rooms Inc.
"""

import time
import threading
import logging

from flask import Flask

import config
from models.database import init_db
from mqtt import MQTTClient
from routes.api import api, set_mqtt_client
from routes.pages import pages

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app():
    """Create and configure Flask application."""
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    # Register blueprints
    app.register_blueprint(api)
    app.register_blueprint(pages)

    # Disable caching for development
    @app.after_request
    def add_no_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app


def run_timeout_checker(mqtt_client):
    """Background thread to check for ping timeouts."""
    while True:
        mqtt_client.check_timeouts()
        time.sleep(0.5)


def main():
    print()
    print("=" * 60)
    print("  ⚗️  WatchTower V2 — Alchemy Escape Rooms")
    print("  📖  Grimoire Operations Dashboard")
    print("=" * 60)
    print()

    # Initialize database
    init_db(config.DATABASE_PATH)
    logger.info(f"Database initialized at {config.DATABASE_PATH}")

    # Initialize MQTT
    mqtt_client = MQTTClient()
    if not mqtt_client.connect():
        print(f"⚠️  Could not connect to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}")
        print(f"   Dashboard will work but device status won't update.")
    else:
        print(f"✓  Connected to MQTT broker at {config.MQTT_BROKER}:{config.MQTT_PORT}")

    # Wire MQTT client into API routes
    set_mqtt_client(mqtt_client)

    # Start timeout checker
    timeout_thread = threading.Thread(target=run_timeout_checker, args=(mqtt_client,), daemon=True)
    timeout_thread.start()

    # Create Flask app
    app = create_app()

    print()
    print(f"🌐  Dashboard: http://localhost:{config.FLASK_PORT}")
    print(f"📡  Devices: {len(mqtt_client.devices)} registered")
    print(f"📋  ClickUp List: {config.CLICKUP_LIST_ID}")
    print()
    print("Press Ctrl+C to stop")
    print()

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    main()
