from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(".recovery") / "access_control.db"
BOOTSTRAP_PATH = Path(".recovery") / "bootstrap_admin_access.txt"
ITERATIONS = 220_000
MAX_FAILED_ATTEMPTS = 8
LOCKOUT_MINUTES = 10
PERMANENT_ADMIN_NAME = os.environ.get("LAZZYBIOINTEL_PERMANENT_ADMIN_NAME", "Anudit Khatri")
PERMANENT_ADMIN_CODE = os.environ.get("LAZZYBIOINTEL_PERMANENT_ADMIN_CODE", "596070")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    return " ".join((name or "").strip().split()).lower()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _hash_code(code: str, salt_hex: str, iterations: int = ITERATIONS) -> str:
    key = hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    )
    return key.hex()


def _verify_code(code: str, salt_hex: str, expected_hash: str, iterations: int) -> bool:
    return hmac.compare_digest(_hash_code(code, salt_hex, iterations), expected_hash)


def _valid_code(code: str) -> bool:
    return bool(code) and code.isdigit() and len(code) == 6


def init_access_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                norm_name TEXT UNIQUE NOT NULL,
                code_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                iterations INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT,
                norm_name TEXT,
                success INTEGER NOT NULL,
                reason TEXT,
                client_ip TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def _log_login(
    full_name: str,
    norm_name: str,
    success: bool,
    reason: str,
    client_ip: str = "unknown",
    user_agent: str = "unknown",
) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO login_events (
                full_name, norm_name, success, reason, client_ip, user_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (full_name, norm_name, 1 if success else 0, reason, client_ip, user_agent, _utc_now_iso()),
        )


def _is_locked(norm_name: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM login_events
            WHERE norm_name = ? AND success = 0 AND created_at >= ?
            """,
            (norm_name, cutoff),
        ).fetchone()
    return bool(row and row["c"] >= MAX_FAILED_ATTEMPTS)


def ensure_bootstrap_admin() -> Optional[tuple[str, str]]:
    full_name = " ".join((PERMANENT_ADMIN_NAME or "").strip().split())
    code = (PERMANENT_ADMIN_CODE or "").strip()
    if not full_name:
        raise ValueError("Permanent admin name cannot be empty.")
    if not _valid_code(code):
        raise ValueError("Permanent admin code must be exactly 6 digits.")

    norm_name = _normalize_name(full_name)
    now = _utc_now_iso()
    created = False

    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE norm_name = ?",
            (norm_name,),
        ).fetchone()

        salt = secrets.token_hex(16)
        code_hash = _hash_code(code, salt)
        if row:
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, code_hash = ?, salt = ?, iterations = ?, role = 'admin', active = 1, updated_at = ?
                WHERE id = ?
                """,
                (full_name, code_hash, salt, ITERATIONS, now, int(row["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (
                    full_name, norm_name, code_hash, salt, iterations, role, active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'admin', 1, ?, ?)
                """,
                (full_name, norm_name, code_hash, salt, ITERATIONS, now, now),
            )
            created = True

    BOOTSTRAP_PATH.parent.mkdir(exist_ok=True)
    BOOTSTRAP_PATH.write_text(
        f"full_name: {full_name}\ncomputer_code: {code}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(BOOTSTRAP_PATH, 0o600)
    except OSError:
        pass

    return (full_name, code) if created else None


def authenticate_user(
    full_name: str,
    computer_code: str,
    client_ip: str = "unknown",
    user_agent: str = "unknown",
) -> tuple[bool, str, Optional[dict]]:
    norm_name = _normalize_name(full_name)
    if not norm_name:
        return False, "Full name is required.", None
    if not _valid_code(computer_code):
        return False, "Computer code must be exactly 6 digits.", None
    if _is_locked(norm_name):
        _log_login(full_name, norm_name, False, "locked_out", client_ip, user_agent)
        return False, f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes.", None

    with _conn() as conn:
        user = conn.execute(
            """
            SELECT id, full_name, norm_name, code_hash, salt, iterations, role, active
            FROM users
            WHERE norm_name = ?
            """,
            (norm_name,),
        ).fetchone()

        if not user:
            _log_login(full_name, norm_name, False, "name_not_found", client_ip, user_agent)
            return False, "Name/code not found.", None
        if int(user["active"]) != 1:
            _log_login(user["full_name"], norm_name, False, "inactive_user", client_ip, user_agent)
            return False, "Access disabled for this user.", None
        if not _verify_code(computer_code, user["salt"], user["code_hash"], int(user["iterations"])):
            _log_login(user["full_name"], norm_name, False, "invalid_code", client_ip, user_agent)
            return False, "Name/code not found.", None

        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (_utc_now_iso(), _utc_now_iso(), int(user["id"])),
        )

    _log_login(user["full_name"], norm_name, True, "login_success", client_ip, user_agent)
    return True, "Login successful.", {
        "full_name": user["full_name"],
        "role": user["role"],
    }


def upsert_user(full_name: str, computer_code: str, role: str = "staff", active: bool = True) -> str:
    clean_name = " ".join((full_name or "").strip().split())
    norm_name = _normalize_name(clean_name)
    if len(clean_name) < 3:
        raise ValueError("Full name must be at least 3 characters.")
    if not _valid_code(computer_code):
        raise ValueError("Computer code must be exactly 6 digits.")
    if role not in {"admin", "staff"}:
        raise ValueError("Role must be admin or staff.")

    salt = secrets.token_hex(16)
    code_hash = _hash_code(computer_code, salt)
    now = _utc_now_iso()

    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE norm_name = ?",
            (norm_name,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, code_hash = ?, salt = ?, iterations = ?, role = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean_name, code_hash, salt, ITERATIONS, role, 1 if active else 0, now, int(row["id"])),
            )
            return "updated"

        conn.execute(
            """
            INSERT INTO users (
                full_name, norm_name, code_hash, salt, iterations, role, active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_name, norm_name, code_hash, salt, ITERATIONS, role, 1 if active else 0, now, now),
        )
    return "created"


def get_users() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, full_name, norm_name, role, active, created_at, updated_at, last_login_at
            FROM users
            ORDER BY role DESC, full_name ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def update_user(
    user_id: int,
    full_name: str,
    computer_code: Optional[str],
    role: str,
    active: bool,
) -> None:
    clean_name = " ".join((full_name or "").strip().split())
    norm_name = _normalize_name(clean_name)
    if len(clean_name) < 3:
        raise ValueError("Full name must be at least 3 characters.")
    if computer_code and not _valid_code(computer_code):
        raise ValueError("Computer code must be exactly 6 digits.")
    if role not in {"admin", "staff"}:
        raise ValueError("Role must be admin or staff.")

    with _conn() as conn:
        current = conn.execute(
            "SELECT id, role, active FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if not current:
            raise ValueError("User not found.")

        if current["role"] == "admin" and role != "admin":
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()
            if admins and int(admins["c"]) <= 1:
                raise ValueError("Cannot remove admin role from the last active admin.")
        if current["role"] == "admin" and int(current["active"]) == 1 and not active:
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()
            if admins and int(admins["c"]) <= 1:
                raise ValueError("Cannot deactivate the last active admin.")

        clash = conn.execute(
            "SELECT id FROM users WHERE norm_name = ? AND id != ?",
            (norm_name, int(user_id)),
        ).fetchone()
        if clash:
            raise ValueError("Another user already exists with this name.")

        now = _utc_now_iso()
        if computer_code:
            salt = secrets.token_hex(16)
            code_hash = _hash_code(computer_code, salt)
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, norm_name = ?, code_hash = ?, salt = ?, iterations = ?, role = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean_name, norm_name, code_hash, salt, ITERATIONS, role, 1 if active else 0, now, int(user_id)),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET full_name = ?, norm_name = ?, role = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (clean_name, norm_name, role, 1 if active else 0, now, int(user_id)),
            )


def delete_user(user_id: int) -> None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, role, active FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if not row:
            raise ValueError("User not found.")
        if row["role"] == "admin" and int(row["active"]) == 1:
            admins = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()
            if admins and int(admins["c"]) <= 1:
                raise ValueError("Cannot delete the last active admin.")
        conn.execute("DELETE FROM users WHERE id = ?", (int(user_id),))


def get_login_events(limit: int = 200) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT full_name, success, reason, client_ip, user_agent, created_at
            FROM login_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]
