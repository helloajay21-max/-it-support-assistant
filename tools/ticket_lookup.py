"""
Tool 2: Ticket Lookup
Searches existing IT support tickets in the local SQLite database.
"""

import os
import sys
from typing import Optional

from langchain_core.tools import tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.init_db import get_db_connection
from utils.logger import get_logger

logger = get_logger(__name__)


def _format_ticket(row) -> str:
    """Format a ticket row into a readable string."""
    status_icons = {
        "Open": "🔴",
        "In Progress": "🟡",
        "Pending Approval": "🟠",
        "Resolved": "🟢",
        "Closed": "⚫"
    }
    icon = status_icons.get(row["status"], "⚪")

    lines = [
        f"🎫 **Ticket ID:** {row['ticket_id']}",
        f"📋 **Title:** {row['title']}",
        f"{icon} **Status:** {row['status']}",
        f"⚡ **Priority:** {row['priority']}",
        f"🏷️ **Category:** {row['category']}",
        f"👤 **Employee:** {row['employee_name']} ({row['employee_id']})",
        f"📝 **Description:** {row['description']}",
        f"📅 **Created:** {row['created_at'][:10]}",
        f"🔄 **Last Updated:** {row['updated_at'][:10]}",
    ]

    if row["assigned_to"]:
        lines.append(f"👷 **Assigned To:** {row['assigned_to']}")

    if row["resolved_at"]:
        lines.append(f"✅ **Resolved On:** {row['resolved_at'][:10]}")

    if row["resolution_notes"]:
        lines.append(f"💡 **Resolution:** {row['resolution_notes']}")

    return "\n".join(lines)


@tool
def ticket_lookup(employee_id: str, ticket_id: Optional[str] = None) -> str:
    """
    Look up IT support tickets for an employee. Can retrieve a specific ticket
    by ticket ID or all tickets for an employee ID.
    Use this tool when the user asks about the status of their tickets,
    wants to see their support history, or references a specific ticket number.

    Args:
        employee_id: The employee's ID (e.g., 'EMP1024').
        ticket_id: Optional specific ticket ID to look up (e.g., 'TKT-2024-001').

    Returns:
        Formatted ticket information or a message if no tickets found.
    """
    logger.info("Ticket lookup called - employee_id: %s, ticket_id: %s", employee_id, ticket_id)

    if not employee_id or not employee_id.strip():
        return "Error: Employee ID is required to look up tickets."

    employee_id = employee_id.strip().upper()
    if not employee_id.startswith("EMP"):
        return f"Error: Invalid employee ID format '{employee_id}'. Expected format: EMP followed by digits (e.g., EMP1024)."

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if ticket_id:
            ticket_id = ticket_id.strip().upper()
            cursor.execute(
                "SELECT * FROM tickets WHERE ticket_id = ? AND employee_id = ?",
                (ticket_id, employee_id)
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                return (
                    f"No ticket found with ID **{ticket_id}** for employee **{employee_id}**. "
                    "Please verify the ticket ID and employee ID are correct."
                )
            return f"📋 **Ticket Details:**\n\n{_format_ticket(row)}"

        else:
            cursor.execute(
                "SELECT * FROM tickets WHERE employee_id = ? ORDER BY created_at DESC",
                (employee_id,)
            )
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return (
                    f"No support tickets found for employee **{employee_id}**. "
                    "You have no open or past tickets in the system."
                )

            open_tickets = [r for r in rows if r["status"] not in ("Resolved", "Closed")]
            resolved_tickets = [r for r in rows if r["status"] in ("Resolved", "Closed")]

            result_parts = [f"📋 **Support Tickets for {employee_id}** — {len(rows)} ticket(s) found:\n"]

            if open_tickets:
                result_parts.append(f"**Active Tickets ({len(open_tickets)}):**\n")
                for row in open_tickets:
                    result_parts.append(_format_ticket(row))
                    result_parts.append("---")

            if resolved_tickets:
                result_parts.append(f"\n**Resolved/Closed Tickets ({len(resolved_tickets)}):**\n")
                for row in resolved_tickets[:3]:  # Show last 3 resolved
                    result_parts.append(_format_ticket(row))
                    result_parts.append("---")
                if len(resolved_tickets) > 3:
                    result_parts.append(f"*...and {len(resolved_tickets) - 3} more resolved ticket(s).*")

            return "\n".join(result_parts)

    except Exception as e:
        logger.error("Ticket lookup error: %s", e, exc_info=True)
        return f"Error retrieving tickets: An unexpected error occurred. Please try again or contact IT helpdesk."
