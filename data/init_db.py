"""
Database initialization script for IT Support Assistant.
Creates and seeds the SQLite database with sample tickets and employees.
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


def init_db():
    """Initialize the SQLite database with schema and sample data."""
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
    # Migration: add notification_shown to pre-existing DBs that lack the column
    try:
        cursor.execute("ALTER TABLE pending_approvals ADD COLUMN notification_shown INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass  # Column already exists

    # Resolve Ajay Kumar's manager name dynamically from JSON data
    _emp1025_manager = "my manager"
    try:
        with open(EMPLOYEES_JSON, "r", encoding="utf-8") as _f:
            _all_emps = json.load(_f)
        _emp1025 = next((e for e in _all_emps if e["employee_id"] == "EMP1025"), {})
        _emp1025_manager = _emp1025.get("manager", "my manager")
    except Exception:
        pass

    sample_tickets = [
        {
            "ticket_id": "TKT-2024-001",
            "employee_id": "EMP1001",
            "employee_name": "Alice Johnson",
            "title": "Cannot connect to VPN from home",
            "description": "Getting 'Authentication failed' error when trying to connect to VPN using Cisco AnyConnect from home network.",
            "category": "VPN",
            "priority": "High",
            "status": "Resolved",
            "created_at": (datetime.now() - timedelta(days=10)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=8)).isoformat(),
            "resolved_at": (datetime.now() - timedelta(days=8)).isoformat(),
            "assigned_to": "IT Team - Network",
            "resolution_notes": "Password was expired. User guided to reset via self-service portal. VPN connection restored."
        },
        {
            "ticket_id": "TKT-2024-002",
            "employee_id": "EMP1024",
            "employee_name": "James Rodriguez",
            "title": "Laptop running very slowly",
            "description": "My laptop has been extremely slow for the past 3 days. Takes 10+ minutes to boot up and applications freeze frequently.",
            "category": "Laptop",
            "priority": "Medium",
            "status": "In Progress",
            "created_at": (datetime.now() - timedelta(days=3)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Hardware",
            "resolution_notes": "Scheduled for memory upgrade. Appointment set for tomorrow."
        },
        {
            "ticket_id": "TKT-2024-003",
            "employee_id": "EMP1004",
            "employee_name": "David Lee",
            "title": "Outlook not syncing emails",
            "description": "Outlook stopped syncing new emails since yesterday morning. Send/Receive shows error 0x800CCC0E.",
            "category": "Email",
            "priority": "High",
            "status": "Open",
            "created_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=1)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Applications",
            "resolution_notes": None
        },
        {
            "ticket_id": "TKT-2024-004",
            "employee_id": "EMP1006",
            "employee_name": "Frank Martinez",
            "title": "Request for Adobe Acrobat Pro installation",
            "description": "Need Adobe Acrobat Pro for creating and editing PDF forms for HR onboarding documents. Manager approved.",
            "category": "Software",
            "priority": "Low",
            "status": "Resolved",
            "created_at": (datetime.now() - timedelta(days=7)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=5)).isoformat(),
            "resolved_at": (datetime.now() - timedelta(days=5)).isoformat(),
            "assigned_to": "IT Team - Software",
            "resolution_notes": "Adobe Acrobat Pro deployed via SCCM. License assigned from pool."
        },
        {
            "ticket_id": "TKT-2024-005",
            "employee_id": "EMP1008",
            "employee_name": "Henry Brown",
            "title": "Cannot access CRM system",
            "description": "Getting 403 Forbidden error when trying to access the Salesforce CRM. Was working fine last week.",
            "category": "Access",
            "priority": "High",
            "status": "Open",
            "created_at": (datetime.now() - timedelta(hours=5)).isoformat(),
            "updated_at": (datetime.now() - timedelta(hours=5)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Access Management",
            "resolution_notes": None
        },
        {
            "ticket_id": "TKT-2024-006",
            "employee_id": "EMP1002",
            "employee_name": "Bob Williams",
            "title": "New monitor request for team member",
            "description": "Requesting a second monitor for Alice Johnson (EMP1001) for development work. Business justification: dual monitor improves coding productivity.",
            "category": "Hardware",
            "priority": "Low",
            "status": "Pending Approval",
            "created_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Hardware",
            "resolution_notes": "Awaiting director approval per hardware request policy."
        },
        {
            "ticket_id": "TKT-2024-007",
            "employee_id": "EMP1003",
            "employee_name": "Carol Davis",
            "title": "WiFi connectivity intermittent in Conference Room B",
            "description": "WiFi keeps dropping every 20-30 minutes in Conference Room B on Floor 3. Affecting meeting productivity.",
            "category": "Network",
            "priority": "Medium",
            "status": "In Progress",
            "created_at": (datetime.now() - timedelta(days=4)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Network",
            "resolution_notes": "Access point identified as faulty. Replacement ordered, ETA 3 days."
        },
        {
            "ticket_id": "TKT-2024-008",
            "employee_id": "EMP1024",
            "employee_name": "James Rodriguez",
            "title": "MFA setup not working on new phone",
            "description": "Got a new company phone and need to set up MFA again. Old phone was wiped. Microsoft Authenticator showing error during QR scan.",
            "category": "MFA",
            "priority": "High",
            "status": "Resolved",
            "created_at": (datetime.now() - timedelta(days=6)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=6)).isoformat(),
            "resolved_at": (datetime.now() - timedelta(days=6)).isoformat(),
            "assigned_to": "IT Team - Identity",
            "resolution_notes": "Old MFA device removed from account. New authenticator setup completed via IT-assisted session."
        },
        {
            "ticket_id": "TKT-2024-009",
            "employee_id": "EMP1025",
            "employee_name": "Ajay Kumar",
            "title": "VPN disconnects repeatedly during work hours",
            "description": "Cisco AnyConnect VPN keeps disconnecting every 15–20 minutes while working from home. Reconnecting is possible but disrupts ongoing meetings and file transfers.",
            "category": "VPN",
            "priority": "High",
            "status": "In Progress",
            "created_at": (datetime.now() - timedelta(days=2)).isoformat(),
            "updated_at": (datetime.now() - timedelta(hours=6)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Network",
            "resolution_notes": "Network logs collected. Suspected MTU mismatch — fix being tested in staging."
        },
        {
            "ticket_id": "TKT-2024-010",
            "employee_id": "EMP1025",
            "employee_name": "Ajay Kumar",
            "title": "Request access to Azure DevOps project board",
            "description": f"Need read/write access to the Capstone-IIT project board in Azure DevOps to push code and review CI/CD pipelines. Approved by manager {_emp1025_manager}.",
            "category": "Access",
            "priority": "Medium",
            "status": "Resolved",
            "created_at": (datetime.now() - timedelta(days=5)).isoformat(),
            "updated_at": (datetime.now() - timedelta(days=4)).isoformat(),
            "resolved_at": (datetime.now() - timedelta(days=4)).isoformat(),
            "assigned_to": "IT Team - Access Management",
            "resolution_notes": "Access granted to Azure DevOps org. User added to Capstone-IIT project with Contributor role."
        },
        {
            "ticket_id": "TKT-2024-011",
            "employee_id": "EMP1025",
            "employee_name": "Ajay Kumar",
            "title": "Laptop screen flickering on external monitor",
            "description": "When connected to an external 4K monitor via HDMI, the display flickers intermittently. Issue started after the latest Windows update. Internal screen is fine.",
            "category": "Hardware",
            "priority": "Low",
            "status": "Open",
            "created_at": (datetime.now() - timedelta(hours=12)).isoformat(),
            "updated_at": (datetime.now() - timedelta(hours=12)).isoformat(),
            "resolved_at": None,
            "assigned_to": "IT Team - Hardware",
            "resolution_notes": None
        }
    ]

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
    print("Sample data loaded successfully.")
