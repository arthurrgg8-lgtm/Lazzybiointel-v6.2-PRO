from __future__ import annotations

from pathlib import Path
import cv2

ALLOWED_EXTS = {".jpg", ".jpeg", ".png"}
MAX_BYTES = 50_000_000  # 50MB
MIN_BYTES = 1024
MIN_W = 50
MIN_H = 50


def validate_image_file(path: str) -> tuple[bool, str]:
    p = Path(path)

    if not p.exists():
        return False, "Missing"
    if not p.is_file():
        return False, "Not a file"

    ext = p.suffix.lower()
    if ext not in ALLOWED_EXTS:
        return False, f"Unsupported format: {ext}"

    size = p.stat().st_size
    if size < MIN_BYTES:
        return False, "File too small"
    if size > MAX_BYTES:
        return False, "File too large (>50MB)"

    # Block traversal-ish patterns only (allow absolute paths)
    s = str(p).replace("\\", "/")
    if "/../" in s or s.startswith("../") or s.endswith("/.."):
        return False, "Unsafe path (traversal)"

    # Corruption / unreadable check
    img = cv2.imread(str(p))
    if img is None:
        return False, "Unreadable / corrupted image"

    h, w = img.shape[:2]
    if h < MIN_H or w < MIN_W:
        return False, "Image too small (<50px)"

    return True, "OK"
