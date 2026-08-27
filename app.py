"""
Streamlit UI for the AI Operations Assistant.
Provides a chat interface with conversation history and tool visibility.
"""

import os
import sys
import time
from datetime import datetime
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()

# Ensure package root is on path
sys.path.insert(0, os.path.dirname(__file__))

from data.init_db import get_db_connection, init_db
from utils.logger import get_logger

logger = get_logger(__name__)

PROJECT_NAME = "AI Operations Assistant Using Agentic AI"
ADMIN_NAME = "Ajay Kumar"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "helloajay21@gmail.com").strip().lower()
ADMIN_EMP_ID = "EMP1025"
DEFAULT_EMPLOYEE_ID = ADMIN_EMP_ID

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title=PROJECT_NAME,
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #0078D4 0%, #005A9E 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { margin: 0; font-size: 1.8rem; }
    .main-header p  { margin: 0.3rem 0 0 0; opacity: 0.85; font-size: 0.95rem; }

    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-open     { background: #ffe0e0; color: #d32f2f; }
    .badge-progress { background: #fff3cd; color: #856404; }
    .badge-resolved { background: #d4edda; color: #155724; }

    .tool-badge {
        background: #e8f4f8;
        border-left: 3px solid #0078D4;
        padding: 0.4rem 0.7rem;
        border-radius: 4px;
        font-size: 0.8rem;
        color: #0078D4;
        margin-bottom: 0.3rem;
    }

    .author-card {
        background: linear-gradient(135deg, rgba(0,120,212,0.08) 0%, rgba(0,90,158,0.12) 100%);
        border: 1px solid rgba(0,120,212,0.18);
        border-radius: 10px;
        padding: 0.8rem 0.9rem;
        margin: 0.5rem 0 0.25rem 0;
        line-height: 1.35;
    }

    .author-card .label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #4b5563;
        margin-bottom: 0.25rem;
    }

    .author-card .name {
        font-weight: 700;
        color: #0f172a;
        font-size: 0.95rem;
    }

    .author-card .email {
        color: #475569;
        font-size: 0.82rem;
        word-break: break-word;
    }

    .stChatMessage { border-radius: 10px; }

    div[data-testid="stSidebarContent"] {
        background-color: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)


# ── Session State Initialization ──────────────────────────────────────────────
def init_session_state():
    """Initialize all Streamlit session state variables."""
    defaults = {
        "messages": [],           # Display messages [(role, content)]
        "agent_state": None,      # LangGraph agent state
        "graph": None,            # Compiled LangGraph
        "db_initialized": False,  # DB setup flag
        "tool_calls_log": [],     # Tool activity log for sidebar
        "turn_count": 0,
        "session_id": str(time.time()),
        "show_db_admin": False,
        "db_admin_mode": "view",
        "db_admin_message": None,
        "current_employee_id": DEFAULT_EMPLOYEE_ID,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def ensure_db():
    """Initialize the SQLite database once per session."""
    if not st.session_state.db_initialized:
        try:
            init_db()
            st.session_state.db_initialized = True
            logger.info("Database initialized")
        except Exception as e:
            logger.error("DB init error: %s", e)
            st.error(f"⚠️ Database initialization failed: {e}")


def _reset_conversation_state() -> None:
    """Clear chat state when the active employee changes."""
    st.session_state.messages = []
    st.session_state.agent_state = None
    st.session_state.tool_calls_log = []
    st.session_state.turn_count = 0
    st.session_state.session_id = str(time.time())


def _get_employee_profile(employee_id: Optional[str]) -> dict:
    """Fetch one employee profile from the DB."""
    if not employee_id:
        return {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT employee_id, name, email, department, role, manager_name, status, created_at
            FROM employees
            WHERE employee_id = ?
            """,
            (employee_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}


def _get_all_employee_profiles() -> list[dict]:
    """Return employee profiles for the active-user selector."""
    return _fetch_db_rows("employees")


def _get_current_employee_profile() -> dict:
    """Resolve the active employee for this Streamlit session."""
    employee_id = st.session_state.get("current_employee_id") or DEFAULT_EMPLOYEE_ID
    profile = _get_employee_profile(employee_id)
    if profile:
        return profile
    fallback = _get_employee_profile(DEFAULT_EMPLOYEE_ID)
    if fallback:
        st.session_state.current_employee_id = fallback["employee_id"]
        return fallback
    return {
        "employee_id": DEFAULT_EMPLOYEE_ID,
        "name": ADMIN_NAME,
        "email": ADMIN_EMAIL,
        "department": "IT",
        "role": "Admin",
        "manager_name": "N/A",
        "status": "Active",
    }


def _current_user_is_admin() -> bool:
    """Return True only for Ajay Kumar's admin profile."""
    profile = _get_current_employee_profile()
    return (
        profile.get("employee_id") == ADMIN_EMP_ID
        and (profile.get("name") or "").strip().lower() == ADMIN_NAME.lower()
        and (profile.get("email") or "").strip().lower() == ADMIN_EMAIL
    )


def _fetch_db_rows(table_name: str) -> list[dict]:
    """Fetch rows from a supported table for DB admin view."""
    queries = {
        "employees": """
            SELECT employee_id, name, email, department, role, manager_name, status, created_at
            FROM employees
            ORDER BY employee_id
        """,
        "tickets": """
            SELECT ticket_id, employee_id, employee_name, title, category, priority, status,
                   created_at, updated_at, resolved_at, assigned_to
            FROM tickets
            ORDER BY created_at DESC
        """,
        "email_dispatch_log": """
            SELECT dispatch_id, employee_id, employee_email, dispatch_type, channel, status, requested_at, details
            FROM email_dispatch_log
            ORDER BY requested_at DESC
        """,
        "pending_approvals": """
            SELECT approval_id, request_type, employee_id, employee_name, employee_email,
                   status, requested_at, resolved_at, result_message
            FROM pending_approvals
            ORDER BY requested_at DESC
        """,
    }
    if table_name not in queries:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(queries[table_name])
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _db_counts() -> tuple[int, int, int, int]:
    """Return (employees_count, tickets_count, email_dispatch_count, pending_approvals_count)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM employees")
    employees_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM tickets")
    tickets_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM email_dispatch_log")
    email_dispatch_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM pending_approvals WHERE status='Pending'")
    approvals_count = int(cursor.fetchone()[0])
    conn.close()
    return employees_count, tickets_count, email_dispatch_count, approvals_count


def _apply_db_row_action(table_name: str, selected_ids: list[str], employee_action: str = "") -> tuple[bool, str]:
    """Apply selected-row action from DB admin panel."""
    if not selected_ids:
        return False, "Please select at least one row."

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ",".join("?" for _ in selected_ids)
        if table_name == "tickets":
            cursor.execute(f"DELETE FROM tickets WHERE ticket_id IN ({placeholders})", tuple(selected_ids))
            deleted = int(cursor.rowcount)
            conn.commit()
            conn.close()
            return True, f"Deleted {deleted} ticket row(s)."

        if table_name == "email_dispatch_log":
            cursor.execute(f"DELETE FROM email_dispatch_log WHERE dispatch_id IN ({placeholders})", tuple(selected_ids))
            deleted = int(cursor.rowcount)
            conn.commit()
            conn.close()
            return True, f"Deleted {deleted} email dispatch row(s)."

        if table_name == "employees":
            if employee_action == "hard_delete":
                cursor.execute(f"DELETE FROM tickets WHERE employee_id IN ({placeholders})", tuple(selected_ids))
                deleted_tickets = int(cursor.rowcount)
                cursor.execute(f"DELETE FROM employees WHERE employee_id IN ({placeholders})", tuple(selected_ids))
                deleted_employees = int(cursor.rowcount)
                conn.commit()
                conn.close()
                return True, f"Hard deleted {deleted_employees} employee row(s) and {deleted_tickets} linked ticket row(s)."

            cursor.execute(
                f"UPDATE employees SET status = 'Inactive' WHERE employee_id IN ({placeholders})",
                tuple(selected_ids),
            )
            updated = int(cursor.rowcount)
            conn.commit()
            conn.close()
            return True, f"Deactivated {updated} employee row(s)."

        conn.close()
        return False, "Unsupported table."
    except Exception as exc:
        conn.close()
        return False, f"DB action failed: {exc}"


def _update_employee_record(employee_id: str, updates: dict) -> tuple[bool, str]:
    """Update editable fields on an existing employee record."""
    allowed = {"name", "email", "department", "role", "manager_name", "status"}
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None and str(v).strip()}
    if not filtered:
        return False, "No valid fields to update."
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        set_clause = ", ".join(f"{k} = ?" for k in filtered)
        cursor.execute(
            f"UPDATE employees SET {set_clause} WHERE employee_id = ?",
            (*filtered.values(), employee_id),
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()
        if updated:
            return True, f"✅ Updated {employee_id}: {', '.join(filtered.keys())}"
        return False, f"Employee {employee_id} not found."
    except Exception as exc:
        return False, f"Update failed: {exc}"


def _get_pending_approval(token: str) -> Optional[dict]:
    """Fetch a pending approval row by token."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_approvals WHERE approval_id = ?", (token,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _update_approval_status(token: str, status: str, result_message: str = "") -> None:
    """Mark an approval as Approved or Rejected."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pending_approvals SET status=?, resolved_at=?, result_message=? WHERE approval_id=?",
            (status, datetime.now().isoformat(), result_message[:2000], token),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to update approval status: %s", exc)


def _execute_approved_action(approval: dict) -> tuple[bool, str]:
    """Execute the stored action for an approved request and notify the employee."""
    import json as _json
    request_type = approval.get("request_type", "")
    try:
        data = _json.loads(approval.get("request_data", "{}"))
    except Exception:
        return False, "Invalid request_data JSON."

    result_msg = ""
    try:
        if request_type == "TICKET_CREATION":
            from tools.ticket_creation import ticket_creation
            result_msg = ticket_creation.invoke({
                "employee_id": data["employee_id"],
                "title":       data.get("title", "IT Support Request"),
                "description": data.get("description", ""),
                "category":    data.get("category", "Other"),
                "priority":    data.get("priority", "Medium"),
            })

        elif request_type == "EMPLOYEE_REGISTRATION":
            from tools.employee_registration import create_employee
            result_msg = create_employee.invoke({
                "name":         data.get("name", ""),
                "email":        data.get("email", ""),
                "department":   data.get("department", ""),
                "manager_name": data.get("manager_name", "N/A"),
                "role":         data.get("role", "Employee"),
            })

        elif request_type == "EMPLOYEE_DELETION":
            from tools.employee_deletion import delete_employee
            result_msg = delete_employee.invoke({
                "employee_id": data["employee_id"],
                "hard_delete": bool(data.get("hard_delete", False)),
            })

        else:
            return False, f"Unknown request_type: {request_type}"

        # Notify employee via email AND store in-app notification
        _notify_employee_both_ways(approval, str(result_msg), approved=True)

        return True, str(result_msg)

    except Exception as exc:
        logger.error("_execute_approved_action error: %s", exc)
        return False, f"Execution error: {exc}"


def _notify_employee_both_ways(
    approval: dict, result_msg: str, approved: bool
) -> dict:
    """
    Notify employee about approval/rejection via TWO channels:
    1. Email  — if a valid email exists in the approval record or the DB
    2. In-app — stores a notification in pending_approvals.result_message
                (notification_shown=0) so the employee sees it in chat on
                their next visit, regardless of email success.

    Returns {"email_sent": bool, "email_error": str}
    """
    import re as _re
    from agent.nodes import _send_email

    emp_email = (approval.get("employee_email") or "").strip()
    emp_name  = approval.get("employee_name", "Employee")
    req_type  = approval.get("request_type", "Request").replace("_", " ").title()

    # If no email in approval record, look it up from the employees table
    if not emp_email or not _re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", emp_email):
        try:
            _conn = get_db_connection()
            _cur  = _conn.cursor()
            _cur.execute("SELECT email FROM employees WHERE employee_id = ?", (approval.get("employee_id", ""),))
            _row = _cur.fetchone()
            _conn.close()
            if _row:
                emp_email = _row["email"].strip()
        except Exception:
            pass

    valid_email = bool(
        emp_email and
        _re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", emp_email)
        and "@autocreated.local" not in emp_email
    )

    # ── Build email content ───────────────────────────────────────────────────
    if approved:
        subject = f"✅ IT Support — Your {req_type} Request Approved & Completed"
        email_body = (
            f"Hello {emp_name},\n\n"
            f"Great news! Your IT support request has been approved and processed.\n\n"
            f"Request Type : {req_type}\n\n"
            f"Result:\n{result_msg}\n\n"
            f"If you have any questions, contact IT Helpdesk.\n"
            f"---\nTechCorp IT Support System"
        )
        notif_heading = "✅ **Your Request Was Approved & Executed**"
        notif_body    = result_msg[:400]
    else:
        subject = f"❌ IT Support — Your {req_type} Request Rejected"
        email_body = (
            f"Hello {emp_name},\n\n"
            f"Your IT support request has been reviewed and rejected by the IT Admin.\n\n"
            f"Request Type : {req_type}\n\n"
            f"If you believe this is an error, please contact IT Helpdesk directly.\n"
            f"---\nTechCorp IT Support System"
        )
        notif_heading = "❌ **Your Request Was Rejected by Admin**"
        notif_body    = "Contact IT Helpdesk if you need assistance."

    # ── Send email ────────────────────────────────────────────────────────────
    email_sent  = False
    email_error = ""
    if valid_email:
        email_sent, email_error = _send_email(emp_email, subject, email_body)
    else:
        email_error = f"No valid email on file (got: '{emp_email}')"

    # ── Build in-app notification message ────────────────────────────────────
    email_status_note = (
        f"\n\n📧 *Confirmation email sent to **{emp_email}**.*"
        if email_sent
        else f"\n\n📧 *Email notification failed — {email_error}. Please check the app for this update.*"
    )
    notification_msg = f"{notif_heading}\n\n**Request:** {req_type}\n\n{notif_body}{email_status_note}"

    # ── Persist as in-app notification (notification_shown=0 → will be shown) ─
    try:
        _conn = get_db_connection()
        _cur  = _conn.cursor()
        _cur.execute(
            "UPDATE pending_approvals SET result_message=?, notification_shown=0 WHERE approval_id=?",
            (notification_msg[:2000], approval.get("approval_id", "")),
        )
        _conn.commit()
        _conn.close()
    except Exception as exc:
        logger.error("Failed to store in-app notification: %s", exc)

    return {"email_sent": email_sent, "email_error": email_error}


def _get_unseen_notifications(employee_id: str) -> list:
    """Return unshown approval notifications for a given employee."""
    if not employee_id:
        return []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT approval_id, request_type, status, result_message, resolved_at
            FROM pending_approvals
            WHERE employee_id = ?
              AND status IN ('Approved', 'Rejected', 'Failed')
              AND (notification_shown IS NULL OR notification_shown = 0)
            ORDER BY resolved_at DESC
            LIMIT 10
        """, (employee_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _mark_notifications_shown(approval_ids: list) -> None:
    """Mark notifications as shown so they don't reappear."""
    if not approval_ids:
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in approval_ids)
        cursor.execute(
            f"UPDATE pending_approvals SET notification_shown=1 WHERE approval_id IN ({placeholders})",
            tuple(approval_ids),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to mark notifications shown: %s", exc)


def _send_response_email(content: str, employee_id: Optional[str] = None) -> tuple[bool, str]:
    """Send an agent response to the employee's registered email."""
    current_profile = _get_current_employee_profile()
    target_email = current_profile.get("email", ADMIN_EMAIL)
    emp_name = current_profile.get("name", ADMIN_NAME)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        eid = employee_id or current_profile.get("employee_id") or DEFAULT_EMPLOYEE_ID
        cursor.execute("SELECT name, email FROM employees WHERE employee_id = ?", (eid,))
        row = cursor.fetchone()
        conn.close()
        if row:
            target_email = row["email"]
            emp_name     = row["name"]
    except Exception:
        pass

    from agent.nodes import _send_email
    subject = f"{PROJECT_NAME} — Response for {emp_name}"
    body = (
        f"Hello {emp_name},\n\n"
        f"Here is your {PROJECT_NAME} response:\n\n"
        f"{content}\n\n"
        f"---\nTechCorp IT Support System"
    )
    return _send_email(target_email, subject, body)


def _render_pending_approval_actions(widget_prefix: str, show_all_rows: bool = True) -> None:
    """Render admin-only approval controls."""
    if not _current_user_is_admin():
        st.warning(f"🔒 Approval actions are available only to {ADMIN_NAME} ({ADMIN_EMAIL}).")
        return

    approval_rows = _fetch_db_rows("pending_approvals")
    pending_rows = [r for r in approval_rows if r.get("status") == "Pending"]

    if not pending_rows:
        st.success("✅ No pending approvals - all caught up!")
        if show_all_rows:
            st.dataframe(approval_rows, use_container_width=True, hide_index=True)
        return

    st.warning(f"⏳ {len(pending_rows)} request(s) awaiting approval")
    st.dataframe(
        approval_rows if show_all_rows else pending_rows,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Approve or reject a request:**")
    option_labels = [
        f"{row['approval_id'][:16]}...  |  {row['request_type']}  |  {row['employee_id']}"
        for row in pending_rows
    ]
    selected_approval = st.selectbox(
        "Select request",
        option_labels,
        key=f"{widget_prefix}_approval_select",
    )
    sel_idx = option_labels.index(selected_approval)
    sel_row = pending_rows[sel_idx]

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✅ Approve & Execute", type="primary", use_container_width=True, key=f"{widget_prefix}_approve_btn"):
            _update_approval_status(sel_row["approval_id"], "Approved", "")
            ok, msg = _execute_approved_action(sel_row)
            if not ok:
                _update_approval_status(sel_row["approval_id"], "Failed", msg)
            st.session_state.db_admin_message = (
                "success" if ok else "error",
                f"{'Approved & employee notified' if ok else 'Failed'}: {msg[:200]}",
            )
            st.rerun()
    with col_b:
        if st.button("❌ Reject", use_container_width=True, key=f"{widget_prefix}_reject_btn"):
            _update_approval_status(sel_row["approval_id"], "Rejected", "Rejected by admin")
            _notify_employee_both_ways(sel_row, "", approved=False)
            st.session_state.db_admin_message = (
                "success",
                f"Rejected & employee notified: {sel_row['approval_id'][:16]}...",
            )
            st.rerun()


def get_agent_graph():
    """Lazily load the LangGraph workflow."""
    if st.session_state.graph is None:
        with st.spinner("🔄 Initializing AI engine..."):
            try:
                from agent.graph import get_graph
                st.session_state.graph = get_graph()
                logger.info("Graph loaded successfully")
            except Exception as e:
                logger.error("Graph load error: %s", e)
                st.error(f"❌ Failed to initialize AI engine: {e}")
                return None
    return st.session_state.graph


# ── Agent invocation ──────────────────────────────────────────────────────────
def run_agent(user_input: str, forced_employee_id: Optional[str] = None) -> Optional[str]:
    """
    Invoke the LangGraph agent with the user's input.

    Returns:
        The AI's response text, or None on error.
    """
    graph = get_agent_graph()
    if graph is None:
        return "❌ AI engine is not available. Please check your API key configuration."

    # Build input for this turn
    new_message = HumanMessage(content=user_input)
    current_profile = _get_current_employee_profile()
    base_employee_id = forced_employee_id or current_profile.get("employee_id")
    base_employee_name = current_profile.get("name")

    # If we have prior state, carry it forward
    if st.session_state.agent_state:
        prior = st.session_state.agent_state
        input_state = {
            "messages": list(prior.messages) + [new_message],
            "employee_id": forced_employee_id or prior.employee_id or base_employee_id,
            "employee_name": prior.employee_name or base_employee_name,
            "intent": prior.intent,
            "pending_ticket": prior.pending_ticket,
            "pending_employee": prior.pending_employee,
            "pending_delete": prior.pending_delete,
            "pending_triage": prior.pending_triage,
            "awaiting_info": prior.awaiting_info,
            "awaiting_field": prior.awaiting_field,
            "tool_output": None,
            "turn_count": prior.turn_count,
        }
    else:
        input_state = {
            "messages": [new_message],
            "employee_id": base_employee_id,
            "employee_name": base_employee_name,
        }

    try:
        result = graph.invoke(input_state)

        # Store updated state
        from agent.state import AgentState
        st.session_state.agent_state = AgentState(**result)

        # Extract last AI message
        ai_messages = [m for m in result.get("messages", []) if isinstance(m, AIMessage)]
        if ai_messages:
            response = ai_messages[-1].content

            # Log tool activity
            intent = result.get("intent")
            if intent and intent != "general":
                tool_map = {
                    "knowledge_search": "🔍 Knowledge Base Search",
                    "ticket_lookup": "🎫 Ticket Lookup",
                    "ticket_creation": "📝 Ticket Creation",
                    "employee_registration": "👤 Employee Registration",
                    "employee_deletion": "🗑️ Employee Deletion",
                }
                tool_label = tool_map.get(intent, intent)
                st.session_state.tool_calls_log.append({
                    "turn": st.session_state.turn_count + 1,
                    "tool": tool_label,
                    "query": user_input[:60] + "..." if len(user_input) > 60 else user_input
                })

            st.session_state.turn_count += 1
            return response
        else:
            return "I processed your request but couldn't generate a response. Please try again."

    except Exception as e:
        logger.error("Agent invocation error: %s", e, exc_info=True)
        return f"❌ An error occurred: {str(e)}\n\nPlease try again or contact IT helpdesk at ext. 4357."


def render_sidebar():
    """Render the sidebar with session info, tools, and quick actions."""
    with st.sidebar:
        current_profile = _get_current_employee_profile()
        employee_rows = _get_all_employee_profiles()
        employee_ids = [row["employee_id"] for row in employee_rows] or [DEFAULT_EMPLOYEE_ID]
        employee_map = {row["employee_id"]: row for row in employee_rows}
        current_employee_id = current_profile.get("employee_id", DEFAULT_EMPLOYEE_ID)
        default_index = employee_ids.index(current_employee_id) if current_employee_id in employee_ids else 0

        st.markdown(f"## 🖥️ {PROJECT_NAME}")
        st.markdown("*Powered by Agentic AI + LangGraph*")
        selected_employee_id = st.selectbox(
            "Using dashboard as",
            employee_ids,
            index=default_index,
            format_func=lambda emp_id: (
                f"{emp_id} — {employee_map.get(emp_id, {}).get('name', emp_id)}"
            ),
            key="current_employee_selector",
        )
        if selected_employee_id != current_employee_id:
            st.session_state.current_employee_id = selected_employee_id
            _reset_conversation_state()
            st.rerun()

        current_profile = _get_current_employee_profile()
        current_name = current_profile.get("name", "Employee")
        current_email = current_profile.get("email", "")
        current_dept = current_profile.get("department", "Unknown")
        current_role = current_profile.get("role", "Employee")
        is_admin = _current_user_is_admin()

        st.markdown(
            f"""
            <div class="author-card">
                <div class="label">Current User</div>
                <div class="name">{current_name}</div>
                <div class="email">{current_email}</div>
                <div class="email" style="margin-top:3px;color:#0078D4;font-weight:600;">
                    🆔 {current_employee_id} &nbsp;·&nbsp; {current_dept} &nbsp;·&nbsp; {current_role}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if is_admin:
            st.success("🔐 Admin approval access enabled")
        else:
            st.caption(f"Admin approvals are restricted to {ADMIN_NAME} ({ADMIN_EMAIL}).")
        st.divider()

        # ── API Status ──
        st.markdown("### ⚙️ Configuration")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_key = os.getenv("OPENAI_API_KEY")

        if azure_endpoint:
            st.success("✅ Azure OpenAI Connected")
        elif openai_key:
            st.success("✅ OpenAI Connected")
        else:
            st.error("❌ No API key configured")
            st.info("Set `OPENAI_API_KEY` or `AZURE_OPENAI_*` in `.env`")

        st.divider()

        # ── Session Info ──
        st.markdown("### 📊 Session Info")
        agent_state = st.session_state.get("agent_state")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Turns", st.session_state.turn_count)
        with col2:
            st.metric("Employee ID", current_employee_id)

        st.caption(f"👤 {current_name}")

        if agent_state and agent_state.awaiting_info:
            field_labels = {
                "employee_id":    "Employee ID",
                "description":    "Issue description",
                "confirmation":   "Confirmation (Yes/No)",
                "emp_name":       "Employee name",
                "emp_email":      "Employee email",
                "emp_department": "Department",
                "emp_manager": "Manager name",
                "emp_role":       "Role / Job title",
                "emp_confirmation": "Confirmation (Yes/No)",
                "delete_employee_id": "Employee ID to delete",
                "delete_mode": "Delete mode (deactivate / hard delete)",
                "delete_confirmation": "Deletion confirmation (Yes/No)",
                "triage_employee_id": "Employee ID",
                "triage_ticket_check": "Check existing tickets? (Yes/No)",
                "new_emp_manager": "Manager name",
            }
            friendly = field_labels.get(agent_state.awaiting_field, agent_state.awaiting_field)
            st.warning(f"⏳ Awaiting: **{friendly}**")

        st.divider()

        # ── Tool Activity Log ──
        st.markdown("### 🔧 Tool Activity")
        if st.session_state.tool_calls_log:
            for entry in reversed(st.session_state.tool_calls_log[-5:]):
                st.markdown(
                    f'<div class="tool-badge">Turn {entry["turn"]}: {entry["tool"]}<br>'
                    f'<small>"{entry["query"]}"</small></div>',
                    unsafe_allow_html=True
                )
        else:
            st.caption("No tools called yet in this session.")

        st.divider()

        # ── Available Tools ──
        st.markdown("### 🛠️ Available Tools")
        tools_info = [
            ("🔍", "Knowledge Search", "How-to guides & troubleshooting"),
            ("🎫", "Ticket Lookup", "Check existing ticket status"),
            ("📝", "Ticket Creation", "Raise a new support ticket"),
            ("👤", "Employee Registration", "Onboard a new employee"),
            ("🗑️", "Employee Deletion", "Deactivate or delete employee records"),
        ]
        for icon, name, desc in tools_info:
            st.markdown(f"**{icon} {name}**  \n{desc}")

        st.divider()

        # ── DB Admin ──
        st.markdown("### 🗄️ DB Admin")
        if st.button("📊 Show DB Details", use_container_width=True):
            st.session_state.show_db_admin = True
            st.session_state.db_admin_mode = "view"
            st.rerun()
        if st.button("🗑️ Delete DB Rows", use_container_width=True):
            st.session_state.show_db_admin = True
            st.session_state.db_admin_mode = "delete"
            st.rerun()
        if st.button("✏️ Update DB Records", use_container_width=True):
            st.session_state.show_db_admin = True
            st.session_state.db_admin_mode = "update"
            st.rerun()
        if st.button("✅ Pending Approvals", use_container_width=True, disabled=not is_admin):
            st.session_state.show_db_admin = True
            st.session_state.db_admin_mode = "approvals"
            st.rerun()

        st.divider()

        # ── Send VPN Setup Email (direct, no conversation loop) ──
        st.markdown("### 📧 Send VPN Setup Email")
        st.caption("Directly send the VPN setup email with temporary password — no back-and-forth needed.")

        vpn_emp_id_input = st.text_input(
            "Employee ID",
            value=current_employee_id,
            key="vpn_email_emp_id",
            placeholder="e.g. EMP1025",
        )
        if st.button("📤 Send VPN Setup Email with Password", use_container_width=True, type="primary", key="send_vpn_email_btn"):
            emp_id_clean = (vpn_emp_id_input or "").strip().upper()
            if not emp_id_clean or not emp_id_clean.startswith("EMP"):
                st.error("❌ Please enter a valid Employee ID (e.g. EMP1025).")
            else:
                try:
                    from data.init_db import get_db_connection as _get_conn
                    _conn = _get_conn()
                    _cursor = _conn.cursor()
                    _cursor.execute(
                        "SELECT name, email FROM employees WHERE employee_id = ?", (emp_id_clean,)
                    )
                    _row = _cursor.fetchone()
                    _conn.close()
                except Exception:
                    _row = None

                if not _row:
                    st.error(f"❌ Employee **{emp_id_clean}** not found in the database.")
                else:
                    _emp_name = _row["name"]
                    _emp_email = _row["email"]
                    with st.spinner(f"Sending VPN setup email to {_emp_email}…"):
                        from agent.nodes import _queue_vpn_email_dispatches
                        _ok, _msg = _queue_vpn_email_dispatches(emp_id_clean, _emp_email, _emp_name)
                    if _ok:
                        st.success(f"✅ VPN setup + password reset emails sent to **{_emp_email}**.")
                    else:
                        st.error(f"⚠️ Email dispatch failed: {_msg}")

        st.divider()

        # ── Quick Prompts — clean labels, personalized messages ──
        st.markdown("### 💬 Quick Prompts")
        # Each entry: (button label shown, message sent to agent, optional forced employee ID)
        quick_prompts = [
            # Knowledge — instant, no state needed
            ("🔑 How to reset VPN password",
             "How do I reset my VPN password? Give me step-by-step instructions.",
             None),
            ("📱 How to set up MFA",
             "How do I set up MFA on my phone? Give me step-by-step guide.",
             None),
            # Ticket lookup — includes EMP ID, goes direct
            (f"🎫 My tickets ({current_employee_id})",
             f"Show all tickets for employee ID {current_employee_id}.",
             current_employee_id),
            ("🏢 Show all employee tickets",
             "Show all tickets for all employees.",
             None),
            # Ticket creation — fully pre-filled, goes straight to confirmation
            (f"💻 Laptop slow — raise ticket",
             (f"My employee ID is {current_employee_id}. My laptop has been very slow for 2 days - "
              f"apps freeze frequently and boot takes over 10 minutes. "
              f"Category: Laptop, Priority: High. Please raise a support ticket."),
             current_employee_id),
            (f"🔒 VPN issue — raise ticket",
             (f"My employee ID is {current_employee_id}. VPN keeps disconnecting every 15 minutes "
              f"while working from home, disrupting meetings. "
              f"Category: VPN, Priority: High. Please raise a ticket."),
             current_employee_id),
            # Registration — one-line format, goes straight to confirmation
            ("👤 Register new employee",
             "Register new employee: Jane Smith, jane.smith@techcorp.com, Engineering, Carol Davis",
             None),
        ]
        for label, message, forced_emp_id in quick_prompts:
            if st.button(label, key=f"qp_{label[:20]}", use_container_width=True):
                st.session_state["pending_quick_prompt"] = message
                st.session_state["pending_quick_emp_id"] = forced_emp_id
                st.rerun()

        st.divider()

        # ── Reset ──
        if st.button("🔄 Clear Conversation", use_container_width=True, type="secondary"):
            st.session_state.messages = []
            st.session_state.agent_state = None
            st.session_state.tool_calls_log = []
            st.session_state.turn_count = 0
            st.session_state.session_id = str(time.time())
            st.rerun()


def render_db_admin_panel():
    """Render DB details and selected-row actions."""
    if not st.session_state.get("show_db_admin"):
        return

    st.markdown("### 🗄️ Database Details")
    mode = st.session_state.get("db_admin_mode", "view")

    employees_count, tickets_count, email_dispatch_count, approvals_count = _db_counts()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Employees", employees_count)
    with c2:
        st.metric("Tickets", tickets_count)
    with c3:
        st.metric("Email Dispatches", email_dispatch_count)
    with c4:
        st.metric("Pending Approvals", approvals_count)

    db_msg = st.session_state.get("db_admin_message")
    if db_msg:
        level, text = db_msg
        if level == "success":
            st.success(text)
        else:
            st.error(text)
        st.session_state.db_admin_message = None

    if mode == "update":
        st.markdown("#### ✏️ Update Employee Record")
        emp_rows = _fetch_db_rows("employees")
        if not emp_rows:
            st.info("No employees found.")
            return
        emp_id_select = st.selectbox(
            "Select Employee to Edit",
            [r["employee_id"] for r in emp_rows],
            key="update_emp_select",
        )
        emp_row = next((r for r in emp_rows if r["employee_id"] == emp_id_select), None)
        if emp_row:
            with st.form("update_employee_form"):
                st.caption(f"Editing: **{emp_id_select}**")
                new_name    = st.text_input("Name",        value=emp_row.get("name", ""))
                new_email   = st.text_input("Email",       value=emp_row.get("email", ""))
                new_dept    = st.text_input("Department",  value=emp_row.get("department", ""))
                new_role    = st.text_input("Role",        value=emp_row.get("role", "Employee"))
                new_manager = st.text_input("Manager Name",value=emp_row.get("manager_name", "N/A"))
                new_status  = st.selectbox(
                    "Status",
                    ["Active", "Inactive"],
                    index=0 if emp_row.get("status", "Active") == "Active" else 1,
                )
                submitted = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)
            if submitted:
                updates = {
                    "name": new_name.strip(), "email": new_email.strip(),
                    "department": new_dept.strip(), "role": new_role.strip(),
                    "manager_name": new_manager.strip(), "status": new_status,
                }
                ok, msg = _update_employee_record(emp_id_select, updates)
                st.session_state.db_admin_message = ("success" if ok else "error", msg)
                st.rerun()
        return

    if mode == "approvals":
        st.markdown("#### ✅ Pending Approvals — Admin Review")
        _render_pending_approval_actions("db_admin", show_all_rows=True)
        return

    st.caption("View all rows in DB. Use delete mode to select and remove specific rows.")

    table_name = st.selectbox(
        "Select table",
        ["employees", "tickets", "email_dispatch_log"],
        key="db_admin_table",
    )
    rows = _fetch_db_rows(table_name)
    st.caption(f"Rows in `{table_name}`: {len(rows)}")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    if mode == "view":
        st.info("Viewing mode active. Click **🗑️ Delete DB Rows** in sidebar to select and delete specific rows.")
        return

    id_field_map = {
        "employees": "employee_id",
        "tickets": "ticket_id",
        "email_dispatch_log": "dispatch_id",
    }
    id_field = id_field_map[table_name]
    selectable_ids = [str(r[id_field]) for r in rows if r.get(id_field)]
    selected_ids = st.multiselect(
        f"Select {table_name} rows by `{id_field}`",
        selectable_ids,
        key=f"db_select_{table_name}",
    )

    employee_action = ""
    if table_name == "employees":
        action_label = st.radio(
            "Employee action",
            [
                "Deactivate selected employees (keep tickets)",
                "Hard delete selected employees + linked tickets",
            ],
            key="db_employee_action",
        )
        employee_action = "hard_delete" if action_label.startswith("Hard delete") else "deactivate"

    if st.button("Apply selected-row action", type="primary", use_container_width=True):
        ok, msg = _apply_db_row_action(table_name, selected_ids, employee_action=employee_action)
        st.session_state.db_admin_message = ("success" if ok else "error", msg)
        st.rerun()


# ── Main Chat Interface ───────────────────────────────────────────────────────
def render_main():
    """Render the main chat interface."""
    current_profile = _get_current_employee_profile()
    current_emp_id = current_profile.get("employee_id", DEFAULT_EMPLOYEE_ID)
    current_name = current_profile.get("name", "Employee")
    is_admin = _current_user_is_admin()

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🖥️ AI Operations Assistant Using Agentic AI</h1>
        <p>Powered by Agentic AI · Ask me anything about IT support operations</p>
    </div>
    """, unsafe_allow_html=True)

    render_db_admin_panel()

    if is_admin:
        pending_admin_rows = [
            row for row in _fetch_db_rows("pending_approvals")
            if row.get("status") == "Pending"
        ]
        if pending_admin_rows:
            st.info(f"🔔 {len(pending_admin_rows)} admin approval request(s) are waiting for action.")
            with st.expander("Open admin approval queue", expanded=True):
                _render_pending_approval_actions("main_admin", show_all_rows=False)

    # ── In-app approval notifications (shown once, then dismissed) ────────────
    unseen = _get_unseen_notifications(current_emp_id)
    if unseen:
        for notif in unseen:
            icon = "✅" if notif["status"] == "Approved" else "❌"
            req_label = notif["request_type"].replace("_", " ").title()
            resolved_on = (notif.get("resolved_at") or "")[:10]
            with st.expander(
                f"{icon} IT Admin Update: **{req_label}** — {resolved_on}",
                expanded=True,
            ):
                st.markdown(notif.get("result_message") or "_No details available._")
        _mark_notifications_shown([n["approval_id"] for n in unseen])
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown(f"""
            👋 **Welcome, {current_name}!**

            I'm your AI operations assistant. I can help you with:
            - 🔍 **Troubleshooting** — Step-by-step guides for common IT issues
            - 🎫 **Ticket Status** — Check your existing support tickets
            - 📝 **Raise a Ticket** — Create a new IT support request
            - 👤 **Employee Registration** — Onboard a new employee into the system
            - 🗑️ **Employee Deletion** — Deactivate or delete an employee from DB

            **Try asking:**
            - *"How do I reset my VPN password?"*
            - *"Check tickets for {current_emp_id}"*
            - *"My laptop won't turn on, please raise a ticket"*
            - *"Register a new employee: Jane Smith, jane@techcorp.com, Engineering, Carol Davis"*
            - *"Delete employee {current_emp_id} (deactivate)"*
            """)
        else:
            for i, msg in enumerate(st.session_state.messages):
                with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        if st.button(
                            "📧 Email this response",
                            key=f"email_resp_{i}",
                            help="Send this response to your registered email address",
                        ):
                            ok, err = _send_response_email(msg["content"], current_emp_id)
                            if ok:
                                st.success("✅ Response sent to your registered email!")
                            else:
                                st.error(f"⚠️ Could not send email: {err}")

    # Handle quick prompt from sidebar
    pending_prompt = st.session_state.pop("pending_quick_prompt", None)
    pending_prompt_emp_id = st.session_state.pop("pending_quick_emp_id", None)

    # Chat input
    user_input = st.chat_input("Type your IT support request here...", key="chat_input")

    # Use quick prompt if set
    if pending_prompt:
        user_input = pending_prompt

    if user_input:
        # Display user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # Generate AI response
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("🤔 Thinking..."):
                response = run_agent(user_input, forced_employee_id=pending_prompt_emp_id if pending_prompt else None)

            if response:
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            else:
                error_msg = "⚠️ Unable to process your request. Please try again."
                st.warning(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

        st.rerun()


def render_approval_callback() -> None:
    """
    Dedicated page for admin approve/reject email callbacks.
    Triggered when the app URL contains ?approve=TOKEN or ?reject=TOKEN.
    """
    params  = st.query_params
    token   = params.get("approve") or params.get("reject")
    is_approve = "approve" in params

    st.markdown(f"""
    <div class="main-header">
        <h1>🔐 {PROJECT_NAME} — Admin Approval Portal</h1>
        <p>TechCorp IT Support System</p>
    </div>
    """, unsafe_allow_html=True)

    if not token:
        st.error("❌ Invalid request — no approval token found.")
        return

    approval = _get_pending_approval(token)
    if not approval:
        st.error("❌ Invalid or expired approval link. The request may have already been processed.")
        return

    if approval["status"] != "Pending":
        icon = "✅" if approval["status"] == "Approved" else "❌"
        st.info(
            f"{icon} This request was already **{approval['status']}** "
            f"on {(approval.get('resolved_at') or '')[:10]}."
        )
        if approval.get("result_message"):
            st.markdown("**Result:**")
            st.markdown(approval["result_message"][:500])
        return

    import json as _json
    request_data = _json.loads(approval.get("request_data", "{}"))

    st.markdown("### 📋 Request Details")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Request Type",  approval["request_type"].replace("_", " ").title())
        st.metric("Employee ID",   approval["employee_id"])
    with col2:
        st.metric("Employee Name", approval["employee_name"])
        st.metric("Requested",     (approval["requested_at"] or "")[:16])

    st.markdown("**Request Data:**")
    st.json(request_data)

    btn_type = "primary" if is_approve else "secondary"

    st.divider()
    if st.button(
        f"{'✅ Approve & Execute' if is_approve else '❌ Reject Request'}",
        type=btn_type,
        use_container_width=True,
    ):
        if is_approve:
            with st.spinner("Executing approved action…"):
                # Set status first so the in-app notification query sees 'Approved'
                _update_approval_status(token, "Approved", "")
                ok, msg = _execute_approved_action(approval)
            if not ok:
                _update_approval_status(token, "Failed", msg)
            if ok:
                st.success(f"✅ **Approved & Executed**\n\n{msg[:400]}")
                st.info("📧 Employee notified via email and in-app notification.")
            else:
                st.error(f"❌ Execution failed: {msg}")
        else:
            _update_approval_status(token, "Rejected", "Rejected by admin via email link")
            _notify_employee_both_ways(approval, "", approved=False)
            st.warning("❌ Request rejected. Employee has been notified via email and in-app.")

    st.divider()
    if st.button(f"🏠 Go to {PROJECT_NAME}", use_container_width=True):
        st.query_params.clear()
        st.rerun()


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    init_session_state()
    ensure_db()

    # Handle admin approval/rejection callbacks from email links
    params = st.query_params
    if "approve" in params or "reject" in params:
        render_approval_callback()
        return

    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
