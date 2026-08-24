"""
Database initialization script for IT Support Assistant.
Creates and seeds the SQLite database with sample tickets.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "tickets.db")


def init_db():
    """Initialize the SQLite database with schema and sample data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_PATH}")
    return DB_PATH


def get_db_connection():
    """Return a database connection."""
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


if __name__ == "__main__":
    init_db()
    print("Sample data loaded successfully.")
