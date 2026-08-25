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

STATUS_ICONS = {
    "Open": "🔴",
    "In Progress": "🟡",
    "Pending Approval": "🟠",
    "Resolved": "🟢",
    "Closed": "⚫",
}
PRIORITY_ICONS = {"Critical": "🚨", "High": "🔥", "Medium": "🔶", "Low": "🔵"}


def _format_ticket(row) -> str:
    """Format a single ticket row into a rich readable block."""
    status_icon = STATUS_ICONS.get(row["status"], "⚪")
    lines = [
        f"🎫 **Ticket ID:** `{row['ticket_id']}`",
        f"📋 **Title:** {row['title']}",
        f"{status_icon} **Status:** {row['status']}",
        f"{PRIORITY_ICONS.get(row['priority'], '🔶')} **Priority:** {row['priority']}",
        f"🏷️ **Category:** {row['category']}",
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


def _employee_profile(cursor, employee_id: str) -> dict:
    """Return employee profile dict (name, role, department, manager_name)."""
    try:
        cursor.execute(
            "SELECT name, role, department, manager_name FROM employees WHERE employee_id = ?",
            (employee_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else {}
    except Exception:
        return {}


@tool
def ticket_lookup(employee_id: str, ticket_id: Optional[str] = None) -> str:
    """
    Look up IT support tickets for an employee. Can retrieve a specific ticket
    by ticket ID or all tickets for an employee ID.
    Use this tool when the user asks about the status of their tickets,
    wants to see their support history, or references a specific ticket number.

    Args:
        employee_id: The employee's ID (e.g., 'EMP1025').
        ticket_id: Optional specific ticket ID to look up (e.g., 'TKT-2024-009').

    Returns:
        Formatted ticket information or a message if no tickets found.
    """
    logger.info("Ticket lookup called - employee_id: %s, ticket_id: %s", employee_id, ticket_id)

    if not employee_id or not employee_id.strip():
        return "Error: Employee ID is required to look up tickets."

    employee_id = employee_id.strip().upper()
    if not employee_id.startswith("EMP"):
        return f"Error: Invalid employee ID format '{employee_id}'. Expected: EMP followed by digits."

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        profile = _employee_profile(cursor, employee_id)

        # ── Single-ticket lookup ───────────────────────────────────────────────
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
                    f"No ticket found with ID `{ticket_id}` for employee `{employee_id}`. "
                    "Please verify both IDs are correct."
                )
            emp_label = profile.get("name", employee_id)
            detail = (
                f"📋 **Ticket Detail — {emp_label} ({employee_id})**\n\n"
                f"{_format_ticket(row)}\n\n"
                f"---\n"
                f"💬 **Need to follow up?** Reply with one of:\n"
                f"- *\"Raise a follow-up ticket for {ticket_id}\"*\n"
                f"- *\"What is the resolution for {ticket_id}?\"*\n"
                f"- *\"Escalate {ticket_id}\"*"
            )
            return detail

        # ── All-tickets lookup ─────────────────────────────────────────────────
        cursor.execute(
            "SELECT * FROM tickets WHERE employee_id = ? ORDER BY created_at DESC",
            (employee_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            emp_name = profile.get("name", employee_id)
            return (
                f"📭 **No tickets found for {emp_name} ({employee_id})**\n\n"
                f"There are currently no open or past IT support tickets in the system.\n\n"
                f"💡 **Need IT help?** I can raise a new support ticket right now.\n"
                f"Just describe your issue and I'll take care of the rest!"
            )

        # ── Employee profile card ─────────────────────────────────────────────
        emp_name = profile.get("name", employee_id)
        profile_lines = [
            f"## 👤 {emp_name} ({employee_id})",
            f"| Field | Details |",
            f"|-------|---------|",
            f"| 🏢 Department | {profile.get('department', 'N/A')} |",
            f"| 💼 Role | {profile.get('role', 'N/A')} |",
            f"| 👔 Manager | {profile.get('manager_name', 'N/A')} |",
            "",
        ]

        open_tickets = [r for r in rows if r["status"] not in ("Resolved", "Closed")]
        resolved_tickets = [r for r in rows if r["status"] in ("Resolved", "Closed")]

        # ── Compact numbered index ────────────────────────────────────────────
        index_lines = [f"### 🗂️ Ticket Summary — {len(rows)} ticket(s) found\n"]
        index_lines.append("| # | Ticket ID | Title | Status | Priority |")
        index_lines.append("|---|-----------|-------|--------|----------|")
        for i, r in enumerate(rows, 1):
            icon = STATUS_ICONS.get(r["status"], "⚪")
            title_short = r["title"][:45] + ("…" if len(r["title"]) > 45 else "")
            index_lines.append(
                f"| {i} | `{r['ticket_id']}` | {title_short} | {icon} {r['status']} | {r['priority']} |"
            )
        index_lines.append("")

        # ── Full detail blocks ────────────────────────────────────────────────
        detail_lines = []
        if open_tickets:
            detail_lines.append(f"---\n### 🔴 Active Tickets ({len(open_tickets)})\n")
            for row in open_tickets:
                detail_lines.append(_format_ticket(row))
                detail_lines.append("")

        if resolved_tickets:
            detail_lines.append(f"---\n### 🟢 Resolved / Closed Tickets ({len(resolved_tickets)})\n")
            for row in resolved_tickets:  # Show ALL resolved — no cap
                detail_lines.append(_format_ticket(row))
                detail_lines.append("")

        # ── Interactive footer ────────────────────────────────────────────────
        footer = (
            "---\n"
            "📌 **Select a ticket for follow-up:**\n"
            "Reply with a Ticket ID to get full details or raise a follow-up request.\n"
            "*Example: \"Show details for TKT-2024-009\"* or *\"Raise follow-up for TKT-2024-011\"*"
        )

        return "\n".join(profile_lines + index_lines + detail_lines + [footer])

    except Exception as e:
        logger.error("Ticket lookup error: %s", e, exc_info=True)
        return "Error retrieving tickets: An unexpected error occurred. Please try again or contact IT helpdesk."
