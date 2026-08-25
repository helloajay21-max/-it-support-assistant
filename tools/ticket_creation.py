"""
Tool 3: Ticket Creation
Creates new IT support tickets in the local SQLite database with validation.
"""

import os
import re
import sys
from datetime import datetime

from langchain_core.tools import tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.init_db import get_db_connection
from utils.logger import get_logger

logger = get_logger(__name__)

VALID_CATEGORIES = {
    "VPN", "Laptop", "Email", "Software", "Hardware",
    "Network", "Password", "Access", "Printer", "MFA",
    "Security", "Account", "Other"
}

VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}


def _load_employees() -> dict:
    """Load employees indexed by employee_id from the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE status = 'Active'")
        rows = cursor.fetchall()
        conn.close()
        return {row["employee_id"]: dict(row) for row in rows}
    except Exception as e:
        logger.error("Failed to load employees from DB: %s", e)
        return {}


def _generate_ticket_id(cursor) -> str:
    """Generate the next sequential ticket ID for the current year."""
    year = datetime.now().year
    cursor.execute(
        "SELECT ticket_id FROM tickets WHERE ticket_id LIKE ? ORDER BY ticket_id DESC LIMIT 1",
        (f"TKT-{year}-%",)
    )
    row = cursor.fetchone()
    if row:
        last_num = int(row["ticket_id"].split("-")[-1])
        return f"TKT-{year}-{last_num + 1:03d}"
    return f"TKT-{year}-001"


def _check_duplicate_ticket(cursor, employee_id: str, title: str, category: str) -> dict | None:
    """Check if a similar open ticket already exists for this employee."""
    cursor.execute(
        """SELECT * FROM tickets
           WHERE employee_id = ?
           AND category = ?
           AND status NOT IN ('Resolved', 'Closed')
           ORDER BY created_at DESC LIMIT 1""",
        (employee_id, category)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def _infer_category(title: str, description: str) -> str:
    """Infer ticket category from title and description keywords."""
    text = (title + " " + description).lower()
    category_keywords = {
        "VPN": ["vpn", "cisco anyconnect", "remote access"],
        "Laptop": ["laptop", "computer", "pc", "slow", "battery", "screen", "keyboard"],
        "Email": ["email", "outlook", "mail", "inbox", "smtp"],
        "Software": ["software", "application", "app", "install", "adobe", "ms office"],
        "Hardware": ["hardware", "monitor", "mouse", "keyboard", "printer", "headset", "webcam"],
        "Network": ["wifi", "wireless", "network", "internet", "ethernet", "connection"],
        "Password": ["password", "locked out", "credentials", "login", "sign in"],
        "Access": ["access", "permission", "forbidden", "unauthorized", "crm", "portal"],
        "Printer": ["printer", "print", "scanner", "copier", "toner"],
        "MFA": ["mfa", "two factor", "2fa", "authenticator"],
        "Security": ["virus", "malware", "phishing", "security", "suspicious", "breach"],
        "Account": ["account", "onboarding", "new employee", "offboarding"]
    }
    for category, keywords in category_keywords.items():
        if any(kw in text for kw in keywords):
            return category
    return "Other"


@tool
def ticket_creation(
    employee_id: str,
    title: str,
    description: str,
    category: str = "Other",
    priority: str = "Medium"
) -> str:
    """
    Create a new IT support ticket in the system.
    Use this tool when the user explicitly asks to raise, create, or log a support ticket.
    Always confirm the details before calling this tool.

    Args:
        employee_id: The employee's ID (e.g., 'EMP1024'). Required.
        title: Short, descriptive title for the issue (max 100 characters). Required.
        description: Detailed description of the issue. Required.
        category: Issue category. One of: VPN, Laptop, Email, Software, Hardware,
                  Network, Password, Access, Printer, MFA, Security, Account, Other.
        priority: Ticket priority. One of: Low, Medium, High, Critical. Default: Medium.

    Returns:
        Confirmation message with the new ticket ID, or an error message.
    """
    logger.info("Ticket creation called - employee_id: %s, title: %s", employee_id, title)

    # --- Input validation ---
    if not employee_id or not employee_id.strip():
        return "❌ Error: Employee ID is required to create a ticket."

    employee_id = employee_id.strip().upper()
    if not re.match(r"^EMP\d{4,}$", employee_id):
        return f"❌ Error: Invalid employee ID format '{employee_id}'. Expected format: EMP followed by 4+ digits."

    if not title or len(title.strip()) < 5:
        return "❌ Error: Ticket title must be at least 5 characters long."

    if not description or len(description.strip()) < 10:
        return "❌ Error: Ticket description must be at least 10 characters. Please provide more detail."

    title = title.strip()[:100]
    description = description.strip()

    # Auto-infer category if not valid
    if category not in VALID_CATEGORIES:
        category = _infer_category(title, description)
        logger.info("Category auto-inferred as: %s", category)

    if priority not in VALID_PRIORITIES:
        priority = "Medium"

    # --- Employee validation ---
    employees = _load_employees()
    if employees and employee_id not in employees:
        return (
            f"❌ Error: Employee ID **{employee_id}** not found in the system. "
            "Please verify your employee ID and try again."
        )
    employee_name = employees.get(employee_id, {}).get("name", "Unknown") if employees else "Unknown"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # --- Duplicate check ---
        existing = _check_duplicate_ticket(cursor, employee_id, title, category)
        if existing:
            conn.close()
            return (
                f"⚠️ **Duplicate Ticket Detected**\n\n"
                f"You already have an open {category} ticket:\n"
                f"🎫 **Ticket ID:** {existing['ticket_id']}\n"
                f"📋 **Title:** {existing['title']}\n"
                f"🔴 **Status:** {existing['status']}\n"
                f"📅 **Created:** {existing['created_at'][:10]}\n\n"
                f"Please check the status of your existing ticket. "
                f"If this is a different issue, please provide more specific details and I will create a new ticket."
            )

        # --- Create ticket ---
        ticket_id = _generate_ticket_id(cursor)
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO tickets
            (ticket_id, employee_id, employee_name, title, description, category,
             priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Open', ?, ?)
        """, (ticket_id, employee_id, employee_name, title, description,
              category, priority, now, now))

        conn.commit()
        conn.close()

        logger.info("Ticket created successfully: %s for %s", ticket_id, employee_id)

        return (
            f"✅ **Support Ticket Created Successfully!**\n\n"
            f"🎫 **Ticket ID:** {ticket_id}\n"
            f"👤 **Employee:** {employee_name} ({employee_id})\n"
            f"📋 **Title:** {title}\n"
            f"🏷️ **Category:** {category}\n"
            f"⚡ **Priority:** {priority}\n"
            f"🔴 **Status:** Open\n"
            f"📅 **Created:** {now[:10]}\n\n"
            f"Our IT team will review your ticket and respond within:\n"
            f"- Critical: 1 hour\n"
            f"- High: 4 hours\n"
            f"- Medium: 1 business day\n"
            f"- Low: 3 business days\n\n"
            f"You can track your ticket status by asking: *'What is the status of {ticket_id}?'*"
        )

    except Exception as e:
        logger.error("Ticket creation error: %s", e, exc_info=True)
        return "❌ Error: Failed to create ticket due to a system error. Please try again or contact IT helpdesk."
