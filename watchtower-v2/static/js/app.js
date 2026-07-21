/* =========================================================================
   WatchTower V2 — Global JavaScript
   Shared utilities across all dashboard pages
   ========================================================================= */

// =============================================================================
// STATUS UPDATES
// =============================================================================

function updateBrokerBadge(connected) {
    const badge = document.getElementById("broker-badge");
    const text = document.getElementById("broker-text");
    if (!badge || !text) return;

    if (connected) {
        badge.className = "broker-badge connected";
        text.textContent = "Broker Connected";
    } else {
        badge.className = "broker-badge disconnected";
        text.textContent = "Disconnected";
    }
}

function updateStatusCounts(counts) {
    if (!counts) return;
    const ids = ["online", "offline", "unknown", "testing"];
    ids.forEach(id => {
        const el = document.getElementById(`count-${id}`);
        if (el) el.textContent = counts[id] || 0;
    });
}

// =============================================================================
// DEVICE COMMANDS
// =============================================================================

function pingAll() {
    fetch("/api/ping-all").then(r => r.json()).then(() => {
        // Status will update on next poll
    });
}

function sendCommand(deviceName, command) {
    fetch(`/api/command/${deviceName}/${command}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                console.error(`Command failed: ${data.error}`);
            }
        });
}

// =============================================================================
// MODAL MANAGEMENT
// =============================================================================

function closeAllModals() {
    const backdrop = document.getElementById("modal-backdrop");
    const container = document.getElementById("modal-container");
    if (backdrop) backdrop.classList.remove("show");
    if (container) container.classList.remove("show");
    setTimeout(() => {
        if (container) container.innerHTML = "";
    }, 300);
}

// Close on Escape
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllModals();
});

// =============================================================================
// SHARED STATUS POLLING (added 2026-07-15 for the redesigned Device Registry)
// Screens subscribe via onStatus(cb); one poller feeds every listener plus
// the global broker badge and the top status-bar counts. Pages that already
// run their own /api/status poll (older templates) are unaffected — they
// just never call onStatus.
// =============================================================================

const _statusListeners = [];
function onStatus(cb) { _statusListeners.push(cb); }

(function sharedStatusPoll() {
    function tick() {
        fetch("/api/status")
            .then(r => r.json())
            .then(data => {
                updateBrokerBadge(data.broker_connected);
                updateStatusCounts(data.counts);
                _statusListeners.forEach(cb => { try { cb(data); } catch (e) { console.error(e); } });
            })
            .catch(() => updateBrokerBadge(false));
    }
    // Only poll on a timer when someone subscribes; otherwise a single
    // initial fetch (below, initStatusPoll) keeps the old behavior.
    setInterval(() => { if (_statusListeners.length) tick(); }, 2000);
    // Give new subscribers a fast first paint.
    setTimeout(() => { if (_statusListeners.length) tick(); }, 50);
})();

// Modal helper for redesigned pages: inject HTML, then use the existing
// show/hide classes (live convention: #modal-container is the centered box).
function openModal(html) {
    const backdrop = document.getElementById("modal-backdrop");
    const container = document.getElementById("modal-container");
    if (!container) return;
    container.innerHTML = html;
    if (backdrop) backdrop.classList.add("show");
    container.classList.add("show");
}

function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
}

// =============================================================================
// UTILITIES
// =============================================================================

function debounce(fn, delay) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// =============================================================================
// INITIAL STATUS CHECK
// =============================================================================

(function initStatusPoll() {
    fetch("/api/status")
        .then(r => r.json())
        .then(data => {
            updateBrokerBadge(data.broker_connected);
            updateStatusCounts(data.counts);
        })
        .catch(() => {
            updateBrokerBadge(false);
        });
})();
