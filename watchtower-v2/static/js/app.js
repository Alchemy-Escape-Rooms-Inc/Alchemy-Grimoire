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
