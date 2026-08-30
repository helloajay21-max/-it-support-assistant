"""
Database initialization script for the AI Operations Assistant.
Creates the SQLite database and preserves operational employee and ticket data
across restarts unless an explicit core-user reset is requested.
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.auth import hash_password

# Respect SQLITE_DB_PATH env var so Azure persistent storage works correctly
DB_PATH = os.environ.get(
    "SQLITE_DB_PATH",
    os.path.join(os.path.dirname(__file__), "tickets.db")
)

EMPLOYEES_JSON = os.path.join(os.path.dirname(__file__), "employees.json")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "helloajay21@gmail.com").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "").strip()
ADMIN_EMPLOYEE_ID = "EMP1025"
ARTI_EMAIL = "artisinha21@gmail.com"
ARTI_EMPLOYEE_ID = "EMP1026"


def _safe_close(conn):
    """Close a sqlite connection quietly."""
    try:
        conn.close()
    except Exception:
        pass


def _configure_connection(conn):
    """Apply sqlite pragmas that reduce lock contention in Streamlit/Azure."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")


def _next_employee_id(cursor) -> str:
    """Generate the next sequential Employee ID."""
    cursor.execute("SELECT MAX(CAST(SUBSTR(employee_id, 4) AS INTEGER)) FROM employees")
    row = cursor.fetchone()
    last_num = row[0] if row and row[0] is not None else 1000
    return f"EMP{last_num + 1}"


def _reconcile_employees_from_tickets(conn):
    """
    Ensure every employee_id present in tickets also exists in employees.
    This protects DB consistency even if older flows created ticket rows first.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO employees
        (employee_id, name, email, department, role, manager_name, status, created_at, username, password_hash, is_admin)
        SELECT
            t.employee_id,
            COALESCE(NULLIF(MAX(t.employee_name), ''), t.employee_id) AS name,
            LOWER(t.employee_id) || '@autocreated.local' AS email,
            'Unknown' AS department,
            'Employee' AS role,
            'N/A' AS manager_name,
            'Active' AS status,
            datetime('now') AS created_at,
            NULL AS username,
            NULL AS password_hash,
            0 AS is_admin
        FROM tickets t
        LEFT JOIN employees e ON e.employee_id = t.employee_id
        WHERE e.employee_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM employees existing_email
              WHERE LOWER(existing_email.email) = LOWER(t.employee_id || '@autocreated.local')
          )
        GROUP BY t.employee_id
        """
    )


def _ensure_admin_profile(conn):
    """Keep Ajay Kumar as the single protected admin profile."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT employee_id, email
        FROM employees
        WHERE LOWER(email) = LOWER(?)
        LIMIT 1
        """,
        (ADMIN_EMAIL,),
    )
    email_owner = cursor.fetchone()

    if email_owner and email_owner["employee_id"] != ADMIN_EMPLOYEE_ID:
        fallback_email = f"{email_owner['employee_id'].lower()}@autocreated.local"
        counter = 1
        while True:
            cursor.execute(
                "SELECT 1 FROM employees WHERE LOWER(email) = LOWER(?) AND employee_id <> ?",
                (fallback_email, email_owner["employee_id"]),
            )
            if not cursor.fetchone():
                break
            fallback_email = f"{email_owner['employee_id'].lower()}.{counter}@autocreated.local"
            counter += 1
        cursor.execute(
            "UPDATE employees SET email = ? WHERE employee_id = ?",
            (fallback_email, email_owner["employee_id"]),
        )

    cursor.execute(
        """
        SELECT employee_id, username
        FROM employees
        WHERE LOWER(COALESCE(username, '')) = LOWER(?)
        LIMIT 1
        """,
        (ADMIN_EMAIL,),
    )
    username_owner = cursor.fetchone()
    if username_owner and username_owner["employee_id"] != ADMIN_EMPLOYEE_ID:
        cursor.execute(
            "UPDATE employees SET username = NULL WHERE employee_id = ?",
            (username_owner["employee_id"],),
        )

    cursor.execute("SELECT created_at FROM employees WHERE employee_id = ?", (ADMIN_EMPLOYEE_ID,))
    existing_admin = cursor.fetchone()
    created_at = existing_admin["created_at"] if existing_admin and existing_admin["created_at"] else datetime.now().isoformat()
    password_hash = hash_password(ADMIN_PASSWORD) if ADMIN_PASSWORD else None

    cursor.execute(
        """
        INSERT OR IGNORE INTO employees
        (employee_id, name, email, department, role, manager_name, status, created_at, username, password_hash, is_admin)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ADMIN_EMPLOYEE_ID,
            "Ajay Kumar",
            ADMIN_EMAIL,
            "IT",
            "Admin",
            "Carol Davis",
            "Active",
            created_at,
            ADMIN_EMAIL,
            password_hash,
            1,
        ),
    )

    if ADMIN_PASSWORD:
        cursor.execute(
            """
            UPDATE employees
            SET name = ?, email = ?, department = ?, role = ?, manager_name = ?, status = ?, username = ?, password_hash = ?, is_admin = 1
            WHERE employee_id = ?
            """,
            (
                "Ajay Kumar",
                ADMIN_EMAIL,
                "IT",
                "Admin",
                "Carol Davis",
                "Active",
                ADMIN_EMAIL,
                password_hash,
                ADMIN_EMPLOYEE_ID,
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE employees
            SET name = ?, email = ?, department = ?, role = ?, manager_name = ?, status = ?, username = COALESCE(username, ?), is_admin = 1
            WHERE employee_id = ?
            """,
            (
                "Ajay Kumar",
                ADMIN_EMAIL,
                "IT",
                "Admin",
                "Carol Davis",
                "Active",
                ADMIN_EMAIL,
                ADMIN_EMPLOYEE_ID,
            ),
        )


def _ensure_arti_profile(conn):
    """Keep Arti as the retained normal user profile."""
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO employees
        (employee_id, name, email, department, role, manager_name, status, created_at, username, password_hash, is_admin)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ARTI_EMPLOYEE_ID,
            "Arti",
            ARTI_EMAIL,
            "Other",
            "Employee",
            "Ajay Kumar",
            "Active",
            datetime.now().isoformat(),
            None,
            None,
            0,
        ),
    )
    cursor.execute(
        """
        UPDATE employees
        SET name = COALESCE(NULLIF(name, ''), ?),
            email = ?,
            department = COALESCE(NULLIF(department, ''), ?),
            role = CASE WHEN is_admin = 1 THEN role ELSE 'Employee' END,
            manager_name = COALESCE(NULLIF(manager_name, ''), ?),
            status = 'Active',
            is_admin = 0
        WHERE employee_id = ?
        """,
        (
            "Arti",
            ARTI_EMAIL,
            "Other",
            "Ajay Kumar",
            ARTI_EMPLOYEE_ID,
        ),
    )


def _should_reset_to_core_users() -> bool:
    """Return True only when an explicit core-data reset was requested."""
    return os.environ.get("RESET_TO_CORE_USERS", "false").strip().lower() in {"1", "true", "yes"}


def _prune_to_core_users(conn):
    """Delete all rows except the protected admin and Arti profiles."""
    cursor = conn.cursor()
    keep_ids = (ADMIN_EMPLOYEE_ID, ARTI_EMPLOYEE_ID)
    placeholders = ",".join("?" for _ in keep_ids)
    cursor.execute("DELETE FROM pending_approvals")
    cursor.execute("DELETE FROM email_dispatch_log")
    cursor.execute("DELETE FROM tickets")
    cursor.execute(
        f"DELETE FROM employees WHERE employee_id NOT IN ({placeholders})",
        keep_ids,
    )


def _cleanup_password_reset_tokens(conn):
    """Delete expired/used password reset tokens while preserving active links."""
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute(
        "DELETE FROM password_reset_tokens WHERE expires_at < ?",
        (now_iso,),
    )
    cursor.execute(
        "DELETE FROM password_reset_tokens WHERE used_at IS NOT NULL",
    )


def _cleanup_login_sessions(conn):
    """Delete expired or revoked login sessions."""
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute(
        "DELETE FROM login_sessions WHERE expires_at < ? OR revoked_at IS NOT NULL",
        (now_iso,),
    )


def _reconcile_approved_ticket_requests(conn):
    """
    Backfill older approved ticket requests that were created before
    the explicit resolved-status update was implemented.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT approval_id, employee_id, request_data, requested_at, resolved_at
            FROM pending_approvals
            WHERE request_type = 'TICKET_CREATION'
              AND status = 'Approved'
            ORDER BY requested_at ASC
            """
        )
        approvals = cursor.fetchall()
    except sqlite3.OperationalError:
        return

    for approval in approvals:
        employee_id = (approval["employee_id"] or "").strip().upper()
        if not employee_id:
            continue

        try:
            request_data = json.loads(approval["request_data"] or "{}")
        except Exception:
            request_data = {}

        title = (request_data.get("title") or "").strip()
        description = (request_data.get("description") or "").strip()
        category = (request_data.get("category") or "Other").strip()
        priority = (request_data.get("priority") or "Medium").strip()
        requested_at = (approval["requested_at"] or "").strip()
        resolved_at = (approval["resolved_at"] or datetime.now().isoformat()).strip()

        if not title or not description:
            continue

        cursor.execute(
            """
            SELECT ticket_id, status
            FROM tickets
            WHERE employee_id = ?
              AND title = ?
              AND description = ?
              AND category = ?
              AND priority = ?
              AND created_at >= ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (employee_id, title, description, category, priority, requested_at or "0000-01-01T00:00:00"),
        )
        ticket_row = cursor.fetchone()

        if not ticket_row:
            cursor.execute(
                """
                SELECT ticket_id, status
                FROM tickets
                WHERE employee_id = ?
                  AND title = ?
                  AND description = ?
                  AND category = ?
                  AND priority = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (employee_id, title, description, category, priority),
            )
            ticket_row = cursor.fetchone()

        if not ticket_row:
            continue
        if ticket_row["status"] in ("Resolved", "Closed"):
            continue

        resolution_notes = (
            "Backfilled resolution: this ticket was approved and executed by admin."
        )
        cursor.execute(
            """
            UPDATE tickets
            SET status = 'Resolved',
                updated_at = ?,
                resolved_at = COALESCE(NULLIF(resolved_at, ''), ?),
                assigned_to = COALESCE(NULLIF(assigned_to, ''), ?),
                resolution_notes = COALESCE(NULLIF(resolution_notes, ''), ?)
            WHERE ticket_id = ?
            """,
            (resolved_at, resolved_at, "Ajay Kumar", resolution_notes, ticket_row["ticket_id"]),
        )


def _prefer_employee_record(*employee_ids: str, conn=None) -> str:
    """Pick the strongest employee record from a set of duplicate rows."""
    ids = [employee_id for employee_id in employee_ids if employee_id]
    if not ids:
        return ""
    if not conn:
        raise ValueError("conn is required")
    cursor = conn.cursor()
    placeholders = ", ".join("?" for _ in ids)
    cursor.execute(
        f"""
        SELECT employee_id, is_admin, username, password_hash, status, created_at
        FROM employees
        WHERE employee_id IN ({placeholders})
        ORDER BY is_admin DESC,
                 CASE WHEN password_hash IS NOT NULL THEN 1 ELSE 0 END DESC,
                 CASE WHEN status = 'Active' THEN 1 ELSE 0 END DESC,
                 created_at ASC
        """,
        ids,
    )
    rows = cursor.fetchall()
    return rows[0]["employee_id"] if rows else ids[0]


def _deduplicate_employee_rows(conn):
    """Repair stale duplicate employee rows before unique indexes are enforced."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT employee_id, email, username
        FROM employees
        ORDER BY is_admin DESC, created_at ASC
        """
    )
    rows = cursor.fetchall()

    email_groups = {}
    username_groups = {}
    for row in rows:
        email = (row["email"] or "").strip().lower()
        username = (row["username"] or "").strip().lower()
        if email:
            email_groups.setdefault(email, []).append(row["employee_id"])
        if username:
            username_groups.setdefault(username, []).append(row["employee_id"])

    # Deduplicate duplicate emails by keeping the strongest record and removing weaker duplicates.
    for email, employee_ids in email_groups.items():
        if len(employee_ids) < 2:
            continue
        keep_id = _prefer_employee_record(*employee_ids, conn=conn)
        for employee_id in employee_ids:
            if employee_id == keep_id:
                continue
            cursor.execute(
                "UPDATE employees SET email = ? WHERE employee_id = ?",
                (f"{employee_id.lower()}@duplicate.invalid", employee_id),
            )
            cursor.execute(
                "DELETE FROM employees WHERE employee_id = ? AND employee_id <> ?",
                (employee_id, keep_id),
            )

    # Deduplicate duplicate usernames by clearing weaker duplicates and preserving one active username.
    for username, employee_ids in username_groups.items():
        if len(employee_ids) < 2:
            continue
        keep_id = _prefer_employee_record(*employee_ids, conn=conn)
        for employee_id in employee_ids:
            if employee_id == keep_id:
                continue
            cursor.execute(
                "UPDATE employees SET username = NULL WHERE employee_id = ? AND employee_id <> ?",
                (employee_id, keep_id),
            )

    conn.commit()


def init_db():
    """Initialize the SQLite database while preserving live users and tickets."""
    # Ensure the parent directory exists (critical for Azure /home/data/ path)
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    cursor = conn.cursor()

    # ── Employees table ────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            employee_id  TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            email        TEXT NOT NULL UNIQUE,
            department   TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'Employee',
            manager_name TEXT NOT NULL DEFAULT 'N/A',
            status       TEXT NOT NULL DEFAULT 'Active',
            created_at   TEXT NOT NULL,
            username     TEXT,
            password_hash TEXT,
            is_admin     INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Migration: add manager_name to pre-existing DBs that lack the column
    try:
        cursor.execute("ALTER TABLE employees ADD COLUMN manager_name TEXT NOT NULL DEFAULT 'N/A'")
    except Exception:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE employees ADD COLUMN username TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE employees ADD COLUMN password_hash TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE employees ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    _deduplicate_employee_rows(conn)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_username_unique ON employees(username) WHERE username IS NOT NULL"
    )

    # Seed employees from JSON if the table is empty
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        try:
            with open(EMPLOYEES_JSON, "r", encoding="utf-8") as f:
                employees = json.load(f)
            seed_ts = datetime.now().isoformat()
            for emp in employees:
                cursor.execute("""
                    INSERT OR IGNORE INTO employees
                    (employee_id, name, email, department, role, manager_name, status, created_at, username, password_hash, is_admin)
                    VALUES (?, ?, ?, ?, ?, ?, 'Active', ?, NULL, NULL, 0)
                """, (
                    emp["employee_id"],
                    emp["name"],
                    emp["email"],
                    emp["department"],
                    emp.get("role", "Employee"),
                    emp.get("manager", "N/A"),
                    seed_ts,
                ))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"Warning: could not seed employees from JSON: {exc}")
    else:
        # Back-fill manager_name for any rows where it is still 'N/A'
        try:
            with open(EMPLOYEES_JSON, "r", encoding="utf-8") as f:
                employees_json = json.load(f)
            for emp in employees_json:
                mgr = emp.get("manager", "N/A")
                if mgr and mgr != "N/A":
                    cursor.execute(
                        "UPDATE employees SET manager_name = ? WHERE employee_id = ? AND manager_name = 'N/A'",
                        (mgr, emp["employee_id"])
                    )
        except Exception:
            pass

    _ensure_admin_profile(conn)

    # ── Tickets table ──────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            employee_name TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'Medium',
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            assigned_to TEXT,
            resolution_notes TEXT
        )
    """)

    # ── Email dispatch log table ───────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_dispatch_log (
            dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            employee_email TEXT NOT NULL,
            dispatch_type TEXT NOT NULL,   -- VPN_FIRST_TIME_SETUP | VPN_PASSWORD_RESET
            channel TEXT NOT NULL DEFAULT 'email',
            status TEXT NOT NULL DEFAULT 'Queued',
            requested_at TEXT NOT NULL,
            details TEXT
        )
    """)

    # ── Pending approvals table ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_approvals (
            approval_id        TEXT PRIMARY KEY,
            request_type       TEXT NOT NULL,
            employee_id        TEXT NOT NULL,
            employee_email     TEXT NOT NULL DEFAULT '',
            employee_name      TEXT NOT NULL DEFAULT '',
            request_data       TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'Pending',
            requested_at       TEXT NOT NULL,
            resolved_at        TEXT,
            result_message     TEXT,
            admin_notes        TEXT,
            notification_shown INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ── Password reset tokens table ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token      TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            email      TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at    TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_employee ON password_reset_tokens(employee_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_expires ON password_reset_tokens(expires_at)"
    )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_sessions (
            token       TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            auth_username TEXT,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            revoked_at  TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_sessions_employee ON login_sessions(employee_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_sessions_expires ON login_sessions(expires_at)"
    )
    # Migration: add notification_shown to pre-existing DBs that lack the column
    try:
        cursor.execute("ALTER TABLE pending_approvals ADD COLUMN notification_shown INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass  # Column already exists

    _ensure_arti_profile(conn)
    if _should_reset_to_core_users():
        _prune_to_core_users(conn)
    _reconcile_approved_ticket_requests(conn)
    _cleanup_password_reset_tokens(conn)
    _cleanup_login_sessions(conn)

    sample_tickets = []

    for ticket in sample_tickets:
        cursor.execute("""
            INSERT OR IGNORE INTO tickets
            (ticket_id, employee_id, employee_name, title, description, category,
             priority, status, created_at, updated_at, resolved_at, assigned_to, resolution_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket["ticket_id"], ticket["employee_id"], ticket["employee_name"],
            ticket["title"], ticket["description"], ticket["category"],
            ticket["priority"], ticket["status"], ticket["created_at"],
            ticket["updated_at"], ticket.get("resolved_at"), ticket.get("assigned_to"),
            ticket.get("resolution_notes")
        ))

    # Keep employees/tickets link integrity in sync
    _reconcile_employees_from_tickets(conn)

    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_PATH}")
    return DB_PATH


def get_db_connection():
    """Return a database connection, initializing the DB if it doesn't exist."""
    if not os.path.exists(DB_PATH):
        init_db()
    # Ensure directory exists even if init_db was skipped (e.g. cold Azure start)
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    _configure_connection(conn)
    return conn


if __name__ == "__main__":
    init_db()
    print("Core user data loaded successfully.")
