"""
Streamlit UI for IT Support Assistant.
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

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IT Support Assistant",
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

        # Send confirmation email to employee
        if approval.get("employee_email"):
            from agent.nodes import _send_email
            emp_name = approval.get("employee_name", "Employee")
            subject  = f"IT Support — Your {request_type.replace('_',' ').title()} Request Approved"
            body = (
                f"Hello {emp_name},\n\n"
                f"Your IT support request has been approved and processed.\n\n"
                f"Request Type : {request_type.replace('_',' ').title()}\n\n"
                f"Result:\n{result_msg}\n\n"
                f"---\nTechCorp IT Support System"
            )
            _send_email(approval["employee_email"], subject, body)

        return True, str(result_msg)

    except Exception as exc:
        logger.error("_execute_approved_action error: %s", exc)
        return False, f"Execution error: {exc}"


def _send_response_email(content: str, employee_id: Optional[str] = None) -> tuple[bool, str]:
    """Send an agent response to the employee's registered email."""
    target_email = AUTHOR_EMAIL
    emp_name     = AUTHOR_NAME
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        eid = employee_id or AUTHOR_EMP_ID
        cursor.execute("SELECT name, email FROM employees WHERE employee_id = ?", (eid,))
        row = cursor.fetchone()
        conn.close()
        if row:
            target_email = row["email"]
            emp_name     = row["name"]
    except Exception:
        pass

    from agent.nodes import _send_email
    subject = f"IT Support Assistant — Response for {emp_name}"
    body = (
        f"Hello {emp_name},\n\n"
        f"Here is your IT Support Assistant response:\n\n"
        f"{content}\n\n"
        f"---\nTechCorp IT Support System"
    )
    return _send_email(target_email, subject, body)


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

    # If we have prior state, carry it forward
    if st.session_state.agent_state:
        prior = st.session_state.agent_state
        input_state = {
            "messages": list(prior.messages) + [new_message],
            "employee_id": forced_employee_id or prior.employee_id,
            "employee_name": prior.employee_name,
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
            "employee_id": forced_employee_id,
            "employee_name": AUTHOR_NAME if forced_employee_id else None,
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


# ── Sidebar ───────────────────────────────────────────────────────────────────

# Author identity — shown in sidebar and used in personalized quick prompts
AUTHOR_NAME     = "Ajay Kumar"
AUTHOR_EMAIL    = "helloajay21@gmail.com"
AUTHOR_EMP_ID   = "EMP1025"
AUTHOR_DEPT     = "IT"


def render_sidebar():
    """Render the sidebar with session info, tools, and quick actions."""
    with st.sidebar:
        st.markdown("## 🖥️ IT Support Assistant")
        st.markdown("*Powered by Agentic AI + LangGraph*")
        st.markdown(
            f"""
            <div class="author-card">
                <div class="label">Project Author</div>
                <div class="name">{AUTHOR_NAME}</div>
                <div class="email">{AUTHOR_EMAIL}</div>
                <div class="email" style="margin-top:3px;color:#0078D4;font-weight:600;">
                    🆔 {AUTHOR_EMP_ID} &nbsp;·&nbsp; {AUTHOR_DEPT}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
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

        # Resolve employee identity: prefer whatever the agent detected,
        # fall back to the known author identity for this deployment
        session_emp_id   = (agent_state.employee_id if agent_state else None) or AUTHOR_EMP_ID
        session_emp_name = (agent_state.employee_name if agent_state else None) or AUTHOR_NAME

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Turns", st.session_state.turn_count)
        with col2:
            st.metric("Employee ID", session_emp_id)

        st.caption(f"👤 {session_emp_name}")

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
        if st.button("✅ Pending Approvals", use_container_width=True):
            st.session_state.show_db_admin = True
            st.session_state.db_admin_mode = "approvals"
            st.rerun()

        st.divider()

        # ── Send VPN Setup Email (direct, no conversation loop) ──
        st.markdown("### 📧 Send VPN Setup Email")
        st.caption("Directly send the VPN setup email with temporary password — no back-and-forth needed.")

        vpn_emp_id_input = st.text_input(
            "Employee ID",
            value=AUTHOR_EMP_ID,
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
            (f"🎫 My tickets ({AUTHOR_EMP_ID})",
             f"Show all tickets for employee ID {AUTHOR_EMP_ID}.",
             AUTHOR_EMP_ID),
            ("🏢 Show all employee tickets",
             "Show all tickets for all employees.",
             None),
            # Ticket creation — fully pre-filled, goes straight to confirmation
            (f"💻 Laptop slow — raise ticket",
             (f"My employee ID is {AUTHOR_EMP_ID}. My laptop has been very slow for 2 days — "
              f"apps freeze frequently and boot takes over 10 minutes. "
              f"Category: Laptop, Priority: High. Please raise a support ticket."),
             AUTHOR_EMP_ID),
            (f"🔒 VPN issue — raise ticket",
             (f"My employee ID is {AUTHOR_EMP_ID}. VPN keeps disconnecting every 15 minutes "
              f"while working from home, disrupting meetings. "
              f"Category: VPN, Priority: High. Please raise a ticket."),
             AUTHOR_EMP_ID),
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
        approval_rows = _fetch_db_rows("pending_approvals")
        pending_rows  = [r for r in approval_rows if r.get("status") == "Pending"]

        if not pending_rows:
            st.success("✅ No pending approvals — all caught up!")
        else:
            st.warning(f"⏳ {len(pending_rows)} request(s) awaiting approval")

        st.dataframe(approval_rows, use_container_width=True, hide_index=True)

        if pending_rows:
            st.markdown("**Manually Approve / Reject:**")
            selected_approval = st.selectbox(
                "Select request",
                [r["approval_id"][:16] + "…  |  " + r["request_type"] + "  |  " + r["employee_id"]
                 for r in pending_rows],
                key="approval_select",
            )
            sel_idx = [r["approval_id"][:16] + "…  |  " + r["request_type"] + "  |  " + r["employee_id"]
                       for r in pending_rows].index(selected_approval)
            sel_row = pending_rows[sel_idx]

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ Approve & Execute", type="primary", use_container_width=True):
                    ok, msg = _execute_approved_action(sel_row)
                    _update_approval_status(sel_row["approval_id"], "Approved" if ok else "Failed", msg)
                    st.session_state.db_admin_message = (
                        "success" if ok else "error",
                        f"{'Approved' if ok else 'Failed'}: {msg[:200]}"
                    )
                    st.rerun()
            with col_b:
                if st.button("❌ Reject", use_container_width=True):
                    _update_approval_status(sel_row["approval_id"], "Rejected", "Rejected by admin")
                    st.session_state.db_admin_message = ("success", f"Rejected: {sel_row['approval_id'][:16]}…")
                    st.rerun()
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

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🖥️ TechCorp IT Support Assistant</h1>
        <p>Powered by Agentic AI · Ask me anything about IT support</p>
    </div>
    """, unsafe_allow_html=True)

    render_db_admin_panel()

    # Display chat history
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown(f"""
            👋 **Welcome, {AUTHOR_NAME}!**

            I'm your AI IT Support Assistant. I can help you with:
            - 🔍 **Troubleshooting** — Step-by-step guides for common IT issues
            - 🎫 **Ticket Status** — Check your existing support tickets
            - 📝 **Raise a Ticket** — Create a new IT support request
            - 👤 **Employee Registration** — Onboard a new employee into the system
            - 🗑️ **Employee Deletion** — Deactivate or delete an employee from DB

            **Try asking:**
            - *"How do I reset my VPN password?"*
            - *"Check tickets for {AUTHOR_EMP_ID}"*
            - *"My laptop won't turn on, please raise a ticket"*
            - *"Register a new employee: Jane Smith, jane@techcorp.com, Engineering, Carol Davis"*
            - *"Delete employee EMP1025 (deactivate)"*
            """)
        else:
            for i, msg in enumerate(st.session_state.messages):
                with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        agent_state = st.session_state.get("agent_state")
                        emp_id = (agent_state.employee_id if agent_state else None) or AUTHOR_EMP_ID
                        if st.button(
                            "📧 Email this response",
                            key=f"email_resp_{i}",
                            help="Send this response to your registered email address",
                        ):
                            ok, err = _send_response_email(msg["content"], emp_id)
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

    st.markdown("""
    <div class="main-header">
        <h1>🔐 IT Support — Admin Approval Portal</h1>
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
                ok, msg = _execute_approved_action(approval)
            _update_approval_status(token, "Approved" if ok else "Failed", msg)
            if ok:
                st.success(f"✅ **Approved & Executed**\n\n{msg[:400]}")
            else:
                st.error(f"❌ Execution failed: {msg}")
        else:
            _update_approval_status(token, "Rejected", "Rejected by admin via email link")
            # Notify employee
            if approval.get("employee_email"):
                from agent.nodes import _send_email
                _send_email(
                    approval["employee_email"],
                    f"IT Support — Your {approval['request_type'].replace('_',' ').title()} Request Rejected",
                    f"Hello {approval.get('employee_name','Employee')},\n\n"
                    f"Your IT support request ({approval['request_type'].replace('_',' ').title()}) "
                    f"has been rejected by the IT Admin.\n\nPlease contact IT helpdesk for more information.\n\n"
                    f"---\nTechCorp IT Support System",
                )
            st.warning("❌ Request rejected. Employee has been notified.")

    st.divider()
    if st.button("🏠 Go to IT Support Assistant", use_container_width=True):
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
