from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

EVIDENCE_ROOT = Path("evidence_locker")


def _safe_name(name: str, fallback: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return fallback
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in raw)
    return cleaned or fallback


def _ext_from_name(name: str, default_ext: str = ".jpg") -> str:
    suffix = Path(name or "").suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"}:
        return suffix
    return default_ext


def save_evidence_pair(
    *,
    ref_bytes: bytes,
    ref_name: str,
    probe_bytes: bytes,
    probe_name: str,
    session_id: str,
) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    day = datetime.now().strftime("%Y-%m-%d")

    evidence_dir = EVIDENCE_ROOT / day / _safe_name(session_id, "session")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    ref_ext = _ext_from_name(ref_name)
    probe_ext = _ext_from_name(probe_name)

    ref_file = evidence_dir / f"{ts}_reference{ref_ext}"
    probe_file = evidence_dir / f"{ts}_probe{probe_ext}"

    ref_file.write_bytes(ref_bytes)
    probe_file.write_bytes(probe_bytes)

    return {
        "dir": str(evidence_dir),
        "reference_file": str(ref_file),
        "probe_file": str(probe_file),
        "reference_sha256": hashlib.sha256(ref_bytes).hexdigest(),
        "probe_sha256": hashlib.sha256(probe_bytes).hexdigest(),
    }

