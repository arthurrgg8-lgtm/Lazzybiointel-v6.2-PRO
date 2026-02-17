import json
import os
import time
from pathlib import Path

RECOVERY_DIR = Path(".recovery")
RECOVERY_DIR.mkdir(exist_ok=True)

STATE_FILE = RECOVERY_DIR / "session_state.json"

def save_session_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)

def restore_session_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def cleanup_old_sessions(max_age_seconds: int = 24 * 3600) -> None:
    if not RECOVERY_DIR.exists():
        return
    now = time.time()
    for p in RECOVERY_DIR.glob("*"):
        try:
            if p.is_file() and (now - p.stat().st_mtime) > max_age_seconds:
                p.unlink()
        except Exception:
            pass

