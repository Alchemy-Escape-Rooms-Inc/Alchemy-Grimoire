"""
alexa_plugs.py — Amazon Smart Plug control through the Alexa cloud
===================================================================
The room's 8 wall switches are Amazon-brand Smart Plugs (the "Amazon-313..322"
hostnames on the eero). They have NO local API — zero open TCP ports, no
Matter — so the only control path from this PC is Amazon's own Alexa web API,
the same calls the phone app makes. alexapy (the library behind Home
Assistant's Alexa integration) handles auth + the phoenix smart-home
endpoints.

Auth model: one interactive Amazon login through a local capture proxy
(2FA-capable). After that a refresh token lives in alexa_data/ (git-ignored)
and the session renews itself. If Amazon ever invalidates it, the Power page
shows the "Link Alexa account" button again — nothing else breaks.

Runs its own asyncio loop in a daemon thread; Flask routes call the sync
wrappers, which bounce coroutines onto that loop.
"""

import asyncio
import json
import logging
import os
import threading

import config

logger = logging.getLogger(__name__)

# Appliance types that belong on the Power page. Amazon Smart Plugs report
# SMARTPLUG; SWITCH/OUTLET cover any future non-Amazon switches on the account.
SWITCHY_TYPES = {"SMARTPLUG", "SWITCH", "OUTLET"}

ACCOUNT_FILE = os.path.join(config.ALEXA_DATA_DIR, "account.json")


class AlexaPlugsManager:
    """Owns the alexapy login + a private asyncio loop (daemon thread)."""

    def __init__(self):
        self.loop = None
        self._thread = None
        self.login = None
        self.proxy = None
        self.proxy_url = ""     # login URL to hand the operator while linking
        self.logged_in = False
        self.linking = False
        self.error = ""
        self.devices = []       # [{entity_id, appliance_id, name, types, on}]
        self.ready = False      # startup restore attempt finished

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self):
        os.makedirs(os.path.join(config.ALEXA_DATA_DIR, ".storage"), exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="alexa-plugs", daemon=True)
        self._thread.start()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._startup())
        self.loop.run_forever()

    async def _startup(self):
        try:
            email = self._saved_email()
            if email:
                await self._restore_session(email)
            else:
                self.error = "Alexa account not linked yet"
        except Exception as e:  # noqa: BLE001 - never let plug auth block launch
            self.error = f"session restore failed: {e}"
            logger.warning("Alexa plugs: %s", self.error)
        self.ready = True

    def _call(self, coro, timeout=60):
        """Run a coroutine on the manager loop from a Flask thread."""
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=timeout)

    # ------------------------------------------------------------------ #
    # auth
    # ------------------------------------------------------------------ #
    def _account(self):
        try:
            with open(ACCOUNT_FILE, encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:  # noqa: BLE001
            return {}

    def _saved_email(self):
        return self._account().get("email", "")

    def _new_login(self, email, otp_secret=""):
        from alexapy import AlexaLogin
        return AlexaLogin(
            url=config.ALEXA_URL,
            email=email,
            password="",
            outputpath=lambda f: os.path.join(config.ALEXA_DATA_DIR, f),
            otp_secret=otp_secret,
        )

    async def _restore_session(self, email):
        self.login = self._new_login(email, self._account().get("otp_secret", ""))
        cookies = await self.login.load_cookie()
        await self.login.login(cookies=cookies)
        if self.login.status.get("login_successful"):
            self.logged_in = True
            self.error = ""
            logger.info("Alexa plugs: session restored for %s", email)
            await self._refresh_devices()
        else:
            self.error = "saved Amazon session expired — relink from the Power page"
            logger.warning("Alexa plugs: %s (status=%s)", self.error, self.login.status)

    async def _begin_login(self, email, host, otp_secret=""):
        from alexapy import AlexaProxy
        # Amazon spaces the authenticator key in groups of 4 — normalize it.
        otp_secret = (otp_secret or "").replace(" ", "").strip()
        if not otp_secret:
            otp_secret = self._account().get("otp_secret", "")
        with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
            json.dump({"email": email, "otp_secret": otp_secret}, f)
        if self.proxy:
            try:
                await self.proxy.stop_proxy()
            except Exception:  # noqa: BLE001
                pass
        self.login = self._new_login(email, otp_secret)
        base_url = f"http://{host}:{config.ALEXA_PROXY_PORT}"
        self.proxy = AlexaProxy(self.login, base_url)
        await self.proxy.start_proxy(host="0.0.0.0")
        self.proxy_url = str(self.proxy.access_url())
        self.linking = True
        self.logged_in = False
        self.error = ""
        asyncio.ensure_future(self._watch_proxy_login())
        logger.info("Alexa plugs: login proxy up at %s", self.proxy_url)
        return self.proxy_url

    async def _watch_proxy_login(self):
        """Poll until the operator finishes the Amazon login (or 15 min)."""
        try:
            for _ in range(180):
                await asyncio.sleep(5)
                if not self.linking:
                    return
                try:
                    if await self.login.test_loggedin():
                        break
                except Exception:  # noqa: BLE001 - mid-login probes can 401
                    continue
            else:
                self.error = "Amazon login timed out — hit Link again"
                self.linking = False
                await self._stop_proxy()
                return
            try:
                await self.login.save_cookiefile()
            except Exception:  # noqa: BLE001 - alexapy usually saved it already
                pass
            self.logged_in = True
            self.linking = False
            self.error = ""
            await self._stop_proxy()
            logger.info("Alexa plugs: account linked")
            await self._refresh_devices()
        except Exception as e:  # noqa: BLE001
            self.error = f"login watcher failed: {e}"
            self.linking = False
            logger.warning("Alexa plugs: %s", self.error)

    async def _stop_proxy(self):
        self.proxy_url = ""
        if self.proxy:
            try:
                await self.proxy.stop_proxy()
            except Exception:  # noqa: BLE001
                pass
            self.proxy = None

    # ------------------------------------------------------------------ #
    # devices + control
    # ------------------------------------------------------------------ #
    async def _refresh_devices(self):
        from alexapy import AlexaAPI
        appliances = await AlexaAPI.get_network_details(self.login) or []
        found = []
        for app in appliances:
            types = set(app.get("applianceTypes") or [])
            if not (types & SWITCHY_TYPES):
                continue
            found.append({
                "entity_id": app.get("entityId", ""),
                "appliance_id": app.get("applianceId", ""),
                "name": app.get("friendlyName", "?"),
                "types": sorted(types),
                "on": None,
            })
        found.sort(key=lambda d: d["name"].lower())
        self.devices = found
        await self._refresh_states()

    async def _refresh_states(self):
        from alexapy import AlexaAPI
        ids = [d["entity_id"] for d in self.devices if d["entity_id"]]
        if not ids:
            return
        try:
            resp = await AlexaAPI.get_entity_state(self.login, entity_ids=ids) or {}
        except Exception as e:  # noqa: BLE001 - state poll is best-effort
            logger.warning("Alexa plugs: state poll failed: %s", e)
            return
        states = {}
        for dev_state in resp.get("deviceStates", []):
            eid = (dev_state.get("entity") or {}).get("entityId", "")
            for cap in dev_state.get("capabilityStates", []):
                try:
                    cap = json.loads(cap) if isinstance(cap, str) else cap
                except Exception:  # noqa: BLE001
                    continue
                if cap.get("name") == "powerState":
                    states[eid] = cap.get("value") == "ON"
        for d in self.devices:
            if d["entity_id"] in states:
                d["on"] = states[d["entity_id"]]

    async def _set_power(self, entity_id, on):
        from alexapy import AlexaAPI
        await AlexaAPI.set_light_state(self.login, entity_id, power_on=on)
        for d in self.devices:
            if d["entity_id"] == entity_id:
                d["on"] = on

    async def _set_all(self, on):
        for d in self.devices:
            try:
                await self._set_power(d["entity_id"], on)
            except Exception as e:  # noqa: BLE001 - keep going, report at end
                logger.warning("Alexa plugs: %s failed: %s", d["name"], e)

    # ------------------------------------------------------------------ #
    # sync API for Flask routes
    # ------------------------------------------------------------------ #
    def status(self):
        return {
            "ready": self.ready,
            "logged_in": self.logged_in,
            "linking": self.linking,
            "login_url": self.proxy_url,
            "email": self._saved_email(),
            "otp_saved": bool(self._account().get("otp_secret")),
            "error": self.error,
            "devices": self.devices,
        }

    def begin_login(self, email, host, otp_secret=""):
        return self._call(self._begin_login(email, host, otp_secret), timeout=30)

    def otp_code(self):
        """Current 6-digit code from the saved authenticator secret.

        Shown in the UI so the operator can (a) finish enabling the
        authenticator app on Amazon and (b) type the code if Amazon asks
        during sign-in. Empty string if no secret is saved yet.
        """
        secret = self._account().get("otp_secret", "")
        if not secret:
            return ""
        try:
            import pyotp
            return pyotp.TOTP(secret).now()
        except Exception as e:  # noqa: BLE001
            logger.warning("Alexa plugs: OTP generation failed: %s", e)
            return ""

    def refresh(self):
        self._call(self._refresh_devices(), timeout=90)
        return self.devices

    def poll_states(self):
        self._call(self._refresh_states(), timeout=45)
        return self.devices

    def set_power(self, entity_id, on):
        self._call(self._set_power(entity_id, on), timeout=30)

    def set_all(self, on):
        self._call(self._set_all(on), timeout=180)


manager = AlexaPlugsManager()
