"""
WatchTower V2 Page Routes
"""
from flask import Blueprint, render_template, abort
import config
from models.grimoire_loader import get_all_sections, get_device_index, get_device_section

pages = Blueprint("pages", __name__)


@pages.route("/")
def dashboard():
    return render_template("dashboard.html")


@pages.route("/mqtt")
def mqtt_feed():
    return render_template("mqtt_feed.html")


@pages.route("/library")
def library():
    grimoire = get_all_sections()
    devices = get_device_index()
    return render_template(
        "library.html",
        gravity_topics=config.GRAVITY_GAMES_TOPICS,
        grimoire=grimoire,
        devices=devices,
    )


@pages.route("/library/device/<slug>")
def device_page(slug):
    device = get_device_section(slug)
    if device is None:
        abort(404)
    return render_template("device_page.html", device=device)


@pages.route("/debug")
def debug_log():
    return render_template("debug_log.html")
