"""
Detached restart helper for Tink's apply_watchtower_changes.

Spawned by chat_api right after a self-edit commit:
    python self_restart.py <watchtower_pid>

Waits ~10 s so Tink can finish her reply, kills WatchTower, starts it fresh,
and health-checks it. If the new code won't serve, the self-edit commit is
reverted, WatchTower is restarted on the old code, and self_edit_rollback.txt
is written so Tink and the operator can see what happened.
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ROLLBACK_FLAG = os.path.join(ROOT, "self_edit_rollback.txt")
HEALTH_URL = "http://localhost:5000/api/chat/history"
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def start_app():
    return subprocess.Popen([sys.executable, "app.py"], cwd=ROOT,
                            close_fds=True, creationflags=DETACHED)


def healthy(tries=30):
    for _ in range(tries):
        try:
            urllib.request.urlopen(HEALTH_URL, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    old_pid = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        os.remove(ROLLBACK_FLAG)  # a fresh apply clears any stale flag
    except OSError:
        pass

    time.sleep(10)  # let Tink deliver her reply before the lights blink
    if old_pid:
        subprocess.run(["taskkill", "/PID", old_pid, "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1.5)

    proc = start_app()
    if healthy():
        return

    # New code won't serve — revert the self-edit and bring back the old code.
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    revert = subprocess.run(["git", "revert", "--no-edit", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1)
    start_app()
    recovered = healthy()
    with open(ROLLBACK_FLAG, "w", encoding="utf-8") as f:
        f.write(
            "Tink's last self-edit failed its health check and was auto-reverted.\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"git revert rc={revert.returncode}: {revert.stdout.strip()[:500]} {revert.stderr.strip()[:500]}\n"
            f"WatchTower recovered on old code: {recovered}\n"
            "The broken change is preserved in git history (the commit before the revert).\n"
        )


if __name__ == "__main__":
    main()
