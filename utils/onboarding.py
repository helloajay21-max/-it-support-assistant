"""
Utility: login provisioning for newly registered employees.

After an employee record is created (admin-direct or via approval), this assigns
a username and emails the employee a one-time link to set their own password.
No password is ever generated, shown in chat, or sent in clear text.
"""

import os
import re
import secrets
from datetime import datetime, timedelta

from data.init_db import get_db_connection
from utils.auth import validate_username
from utils.logger import get_logger

logger = get_logger(__name__)

SETUP_LINK_HOURS = 24
PROJECT_NAME = "AI Operations Assistant"


def build_query_link(query_key: str, token: str) -> str:
    """Build an absolute app URL with a query parameter token."""
    def _normalized(raw: str) -> str:
        cleaned = (raw or "").strip().rstrip("/")
        if not cleaned:
            return ""
        if not re.match(r"^https?://", cleaned, re.IGNORECASE):
            cleaned = f"https://{cleaned.lstrip('/')}"
        return cleaned.rstrip("/")

    configured = _normalized(os.getenv("APP_BASE_URL", ""))
    host = (os.getenv("WEBSITE_HOSTNAME", "") or "").strip().rstrip("/")
    platform = f"https://{host}" if host else ""

    if configured:
        if host and ("localhost" in configured.lower() or "127.0.0.1" in configured):
            base = platform or configured
        else:
            base = configured
    elif platform:
        base = platform
    else:
        base = "http://localhost:8501"
    return f"{base}/?{query_key}={token}"


def _suggest_username(cursor, email: str, name: str) -> str:
    local = (email or "").split("@")[0] or name or "user"
    base = re.sub(r"[^a-zA-Z0-9._-]+", ".", local.lower()).strip(".") or "user"
    base = base[:34]
    if len(base) < 4:
        base = (base + "user")[:34]
    candidate, n = base, 1
    while True:
        cursor.execute("SELECT 1 FROM employees WHERE LOWER(username) = LOWER(?)", (candidate,))
        if not cursor.fetchone() and validate_username(candidate):
            return candidate
        n += 1
        candidate = f"{base}{n}"


def provision_login(employee_id: str) -> dict:
    """
    Ensure the employee has a username and email a password-setup link.
    Returns {"ok", "username", "email", "email_sent", "error"}.
    """
    result = {"ok": False, "username": "", "email": "", "email_sent": False, "error": ""}
    from agent.nodes import _send_email, _is_valid_email

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT employee_id, name, email, username, status FROM employees WHERE employee_id = ?",
            (employee_id,),
        )
        row = cursor.fetchone()
        if not row:
            result["error"] = f"Employee {employee_id} not found."
            return result
        emp = dict(row)
        email = (emp.get("email") or "").strip().lower()
        result["email"] = email

        username = (emp.get("username") or "").strip()
        if not username:
            username = _suggest_username(cursor, email, emp.get("name", ""))
            cursor.execute("UPDATE employees SET username = ? WHERE employee_id = ?", (username, employee_id))
        result["username"] = username

        if not _is_valid_email(email):
            conn.commit()
            result["error"] = f"No valid email on file for {employee_id}."
            return result

        now = datetime.now()
        token = secrets.token_urlsafe(32)
        cursor.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE employee_id = ? AND used_at IS NULL",
            (now.isoformat(), employee_id),
        )
        cursor.execute(
            """
            INSERT INTO password_reset_tokens (token, employee_id, email, created_at, expires_at, used_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (token, employee_id, email, now.isoformat(), (now + timedelta(hours=SETUP_LINK_HOURS)).isoformat()),
        )
        conn.commit()

        link = build_query_link("reset_password", token)
        body = (
            f"Hello {emp.get('name') or 'there'},\n\n"
            f"Your {PROJECT_NAME} account has been approved and created.\n\n"
            f"  Employee ID : {employee_id}\n"
            f"  Username    : {username}\n\n"
            f"Set your password using this one-time link (valid for {SETUP_LINK_HOURS} hours):\n{link}\n\n"
            "Then log in with your username (or email) and the password you chose. "
            "If the link expires, use 'Forgot Password' on the login page.\n"
            "For your security, never share this link with anyone.\n\n"
            f"---\n{PROJECT_NAME}"
        )
        sent_ok, err = _send_email(email, f"{PROJECT_NAME} — Your account is ready", body)
        result.update(ok=True, email_sent=sent_ok, error="" if sent_ok else str(err))
        logger.info("Login provisioned for %s (username=%s, email_sent=%s)", employee_id, username, sent_ok)
        return result
    except Exception as exc:
        logger.error("provision_login failed for %s: %s", employee_id, exc, exc_info=True)
        result["error"] = "System error while provisioning login."
        return result
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def describe_provisioning(prov: dict) -> str:
    """Human-readable summary of a provision_login() result."""
    if not prov.get("ok"):
        return f"⚠️ Account login could not be set up automatically: {prov.get('error')}"
    if prov.get("email_sent"):
        return (
            f"🔐 **Login created** — username **{prov['username']}**. A one-time password-setup link "
            f"was emailed to **{prov['email']}** (valid {SETUP_LINK_HOURS}h)."
        )
    return (
        f"🔐 Username **{prov['username']}** assigned, but the setup email to **{prov['email']}** "
        f"failed ({prov.get('error')}). The employee can use **Forgot Password** on the login page."
    )
