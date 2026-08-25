"""
Tool: Employee Deletion
Supports deactivation or hard deletion of employee records from the database.
"""

import os
import re
import sys

from langchain_core.tools import tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.init_db import get_db_connection
from utils.logger import get_logger

logger = get_logger(__name__)


@tool
def delete_employee(employee_id: str, hard_delete: bool = False) -> str:
    """
    Delete or deactivate an employee record.

    Args:
        employee_id: Employee ID like EMP1025.
        hard_delete: If True, permanently delete employee and all tickets.
                     If False, mark employee status as Inactive and keep tickets.

    Returns:
        Status message describing what was done.
    """
    employee_id = (employee_id or "").strip().upper()
    if not re.match(r"^EMP\d{4,}$", employee_id):
        return f"❌ Invalid employee ID '{employee_id}'. Expected format EMP####."

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT employee_id, name, status FROM employees WHERE employee_id = ?",
            (employee_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return f"❌ Employee `{employee_id}` does not exist in the database."

        employee_name = row["name"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM tickets WHERE employee_id = ?", (employee_id,))
        ticket_count = cursor.fetchone()["cnt"]

        if hard_delete:
            cursor.execute("DELETE FROM tickets WHERE employee_id = ?", (employee_id,))
            cursor.execute("DELETE FROM employees WHERE employee_id = ?", (employee_id,))
            conn.commit()
            conn.close()
            logger.info("Hard deleted employee %s and %s tickets", employee_id, ticket_count)
            return (
                f"🗑️ **Hard deletion completed**\n\n"
                f"- Employee: {employee_name} ({employee_id})\n"
                f"- Deleted tickets: {ticket_count}\n"
                f"- Employee record removed permanently."
            )

        cursor.execute(
            "UPDATE employees SET status = 'Inactive' WHERE employee_id = ?",
            (employee_id,)
        )
        conn.commit()
        conn.close()
        logger.info("Deactivated employee %s", employee_id)
        return (
            f"✅ **Employee deactivated**\n\n"
            f"- Employee: {employee_name} ({employee_id})\n"
            f"- Status: Inactive\n"
            f"- Existing tickets kept: {ticket_count}"
        )
    except Exception as exc:
        logger.error("delete_employee failed: %s", exc, exc_info=True)
        return "❌ Failed to delete/deactivate employee due to a system error."
