"""
Tink MCP bridge — stdio MCP server the Claude Code CLI launches for chat turns.
================================================================================
Every tool Tink has (device registry, MQTT feed, game state, self-edit pipeline,
notebook, ...) lives inside the running WatchTower process. This tiny server
speaks MCP (newline-delimited JSON-RPC over stdio) to the Claude CLI and
forwards each tool call to WatchTower's loopback-only bridge endpoints in
routes/chat_api.py, so the tool implementations stay exactly where they were.

Launched by the CLI via --mcp-config (see chat_api._mcp_config); never run by
hand. Stdlib only — no third-party deps.
"""

import json
import os
import sys
import urllib.error
import urllib.request

BRIDGE = os.environ.get("TINK_BRIDGE_URL", "http://127.0.0.1:5000")
TOKEN = os.environ.get("TINK_BRIDGE_TOKEN", "")
PROTOCOL_FALLBACK = "2025-06-18"
CALL_TIMEOUT_S = 330  # run_command can legally take 300s


def _http(method, path, payload=None, timeout=CALL_TIMEOUT_S):
    req = urllib.request.Request(
        BRIDGE + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Tink-Token": TOKEN},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _list_tools():
    try:
        return _http("GET", "/api/tink-tools/catalog", timeout=15)["tools"]
    except Exception as e:  # noqa: BLE001 - a dead bridge must not kill the MCP handshake
        print(f"tink_mcp_server: catalog fetch failed: {e}", file=sys.stderr)
        return []


def _call_tool(name, arguments):
    try:
        out = _http("POST", "/api/tink-tools/exec", {"name": name, "input": arguments or {}})
        return {"content": [{"type": "text", "text": out.get("result", "")}], "isError": False}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {
            "content": [{"type": "text", "text": f"Bridge error calling {name}: {e} — "
                                                 f"is WatchTower up on {BRIDGE}?"}],
            "isError": True,
        }


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        mid = msg.get("id")
        method = msg.get("method", "")
        if method == "initialize":
            ver = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_FALLBACK
            result = {"protocolVersion": ver, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "watchtower", "version": "2.0.0"}}
        elif method == "tools/list":
            result = {"tools": _list_tools()}
        elif method == "tools/call":
            p = msg.get("params") or {}
            result = _call_tool(p.get("name", ""), p.get("arguments"))
        elif method == "ping":
            result = {}
        elif mid is None:
            continue  # notification (e.g. notifications/initialized) — no reply
        else:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"Unknown method: {method}"}})
            continue
        if mid is not None:
            _send({"jsonrpc": "2.0", "id": mid, "result": result})


if __name__ == "__main__":
    main()
