"""
Tool 4: Employee Registration
Creates new employee records in the database with full validation.
"""

import os
import re
import sys
from datetime import datetime

from typing import Optional

from langchain_core.tools import tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.init_db import get_db_connection
from utils.logger import get_logger

logger = get_logger(__name__)

VALID_DEPARTMENTS = {
    "Engineering", "IT", "Finance", "HR", "Sales",
    "Marketing", "Operations", "Legal", "Product", "Design", "Other"
}

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _next_employee_id(cursor) -> str:
    """Generate the next sequential Employee ID (e.g. EMP1025)."""
    cursor.execute(
        "SELECT MAX(CAST(SUBSTR(employee_id, 4) AS INTEGER)) FROM employees"
    )
    row = cursor.fetchone()
    last_num = row[0] if row and row[0] is not None else 1000
    return f"EMP{last_num + 1}"


def _employee_exists_by_email(cursor, email: str) -> dict | None:
    """Return the existing employee row if the email is already registered."""
    cursor.execute("SELECT * FROM employees WHERE LOWER(email) = LOWER(?)", (email,))
    row = cursor.fetchone()
    return dict(row) if row else None


@tool
def create_employee(
    name: str,
    email: str,
    department: str,
    manager_name: str,
    role: str = "Employee",
    employee_id: Optional[str] = None,
) -> str:
    """
    Register a new employee in the IT support system.
    Use this tool when IT support needs to onboard a new employee so they can
    raise tickets and access IT services.

    The tool:
    1. Validates all required fields (name, email, department, manager_name).
    2. Checks that the email address is not already registered.
    3. Uses the preferred employee_id if provided and available, otherwise
       generates the next unique sequential Employee ID automatically.
    4. Stores the employee record with status 'Active'.
    5. Returns the new Employee ID and full record summary.

    Args:
        name:        Full name of the new employee (e.g. 'Ajay Kumar'). Required.
        email:       Work email address (e.g. 'ajay@techcorp.com'). Required. Must be unique.
        department:  Department name (e.g. 'Engineering', 'IT', 'Finance', 'HR', 'Sales').
                     Required.
        manager_name: Reporting manager full name (e.g. 'Carol Davis'). Required.
        role:        Job title / role (e.g. 'Software Engineer'). Defaults to 'Employee'.
        employee_id: Optional preferred Employee ID (e.g. 'EMP1025'). Used when the caller
                     wants to preserve a specific ID (e.g. auto-registration during ticket
                     creation). Falls back to auto-generation if already taken.

    Returns:
        A success message with the new Employee ID, or a descriptive error message.
    """
    logger.info("create_employee called — name=%s, email=%s, dept=%s, manager=%s", name, email, department, manager_name)

    # ── Field validation ───────────────────────────────────────────────────────
    name = (name or "").strip()
    email = (email or "").strip()
    department = (department or "").strip()
    manager_name = (manager_name or "").strip()
    role = (role or "Employee").strip() or "Employee"

    errors = []
    if not name or len(name) < 2:
        errors.append("**Name** must be at least 2 characters.")
    if not email:
        errors.append("**Email** is required.")
    elif not EMAIL_RE.match(email):
        errors.append(f"**Email** '{email}' is not a valid email address.")
    if not department or len(department) < 2:
        errors.append("**Department** must be at least 2 characters.")
    if not manager_name or len(manager_name) < 2:
        errors.append("**Manager name** must be at least 2 characters.")

    if errors:
        return "❌ Validation failed:\n" + "\n".join(f"  • {e}" for e in errors)

    # Normalise department casing (case-insensitive match to known depts)
    dept_lower = department.lower()
    matched_dept = next(
        (d for d in VALID_DEPARTMENTS if d.lower() == dept_lower),
        department.title()  # Preserve title-case if unknown
    )

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ── Uniqueness check ───────────────────────────────────────────────────
        existing = _employee_exists_by_email(cursor, email)
        if existing:
            conn.close()
            return (
                f"❌ **Email already registered**\n\n"
                f"An employee with email **{email}** already exists:\n"
                f"  🆔 Employee ID : {existing['employee_id']}\n"
                f"  👤 Name        : {existing['name']}\n"
                f"  🏢 Department  : {existing['department']}\n"
                f"  📌 Status      : {existing['status']}\n\n"
                f"If you need to update existing employee details, please contact HR."
            )

        # ── Generate / resolve Employee ID ───────────────────────────────────────
        new_emp_id = None
        if employee_id:
            preferred = employee_id.strip().upper()
            if re.match(r"^EMP\d{4,}$", preferred):
                cursor.execute("SELECT 1 FROM employees WHERE employee_id = ?", (preferred,))
                if not cursor.fetchone():
                    new_emp_id = preferred  # Preferred ID is available — use it
        if new_emp_id is None:
            new_emp_id = _next_employee_id(cursor)

        now = datetime.now().isoformat()

        # ── Insert record ─────────────────────────────────────────────────────
        cursor.execute("""
            INSERT INTO employees (employee_id, name, email, department, role, manager_name, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Active', ?)
        """, (new_emp_id, name, email, matched_dept, role, manager_name, now))

        conn.commit()
        conn.close()

        logger.info("Employee created: %s (%s)", new_emp_id, name)

        return (
            f"✅ **Employee Registered Successfully!**\n\n"
            f"  🆔 Employee ID  : **{new_emp_id}**\n"
            f"  👤 Name         : {name}\n"
            f"  📧 Email        : {email}\n"
            f"  🏢 Department   : {matched_dept}\n"
            f"  👔 Manager      : {manager_name}\n"
            f"  💼 Role         : {role}\n"
            f"  📌 Status       : Active\n"
            f"  📅 Created At   : {now[:10]}\n\n"
            f"The employee can now raise IT support tickets using their Employee ID: **{new_emp_id}**"
        )

    except Exception as exc:
        logger.error("create_employee error: %s", exc, exc_info=True)
        return "❌ Error: Failed to register employee due to a system error. Please try again."
