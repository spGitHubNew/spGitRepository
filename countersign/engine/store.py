"""Local persistence: decisions, statuses, register confirmations, uploads, and an append-only audit log (FR-38)."""

import json
import threading
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
STATE = DATA / "state.json"
AUDIT = DATA / "audit.jsonl"
UPLOADS = DATA / "uploads"
_lock = threading.RLock()

EMPTY = {"decisions": {}, "status": {}, "feedback": {}, "register": {"confirmations": {}, "extracted": []},
         "uploads": {}, "intake_overrides": {}}


def now():
    return datetime.now().isoformat(timespec="seconds")


def load():
    with _lock:
        if not STATE.exists():
            return json.loads(json.dumps(EMPTY))
        data = json.loads(STATE.read_text(encoding="utf-8"))
        for k, v in EMPTY.items():
            data.setdefault(k, json.loads(json.dumps(v)))
        return data


def save(state):
    with _lock:
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE)


def audit(event, user, **details):
    """Append-only: lines are only ever added, never rewritten."""
    with _lock:
        DATA.mkdir(parents=True, exist_ok=True)
        rec = {"at": now(), "event": event, "user": user, **details}
        with AUDIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


def read_audit(limit=500):
    if not AUDIT.exists():
        return []
    lines = AUDIT.read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lines[-limit:]][::-1]


def reset():
    """Demo reset: clears decisions and statuses. The audit log is kept and the reset itself is logged."""
    with _lock:
        if STATE.exists():
            STATE.unlink()
    audit("demo_reset", "system", note="State cleared; audit log retained (append-only)")
