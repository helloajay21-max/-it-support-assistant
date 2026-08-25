"""
Streamlit UI for IT Support Assistant.
Provides a chat interface with conversation history and tool visibility.
"""

import os
import sys
import time
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
    }
    if table_name not in queries:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(queries[table_name])
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def _db_counts() -> tuple[int, int]:
    """Return (employees_count, tickets_count)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM employees")
    employees_count = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM tickets")
    tickets_count = int(cursor.fetchone()[0])
    conn.close()
    return employees_count, tickets_count


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

        st.divider()

        # ── Quick Prompts — clean labels, personalized messages ──
        st.markdown("### 💬 Quick Prompts")
        # Each entry: (button label shown, message sent to agent, optional forced employee ID)
        quick_prompts = [
            ("How do I reset my VPN password?", "How do I reset my VPN password?", None),
            ("Check my ticket status", "What is the status of my tickets?", AUTHOR_EMP_ID),
            ("My laptop is slow — raise a ticket", "My laptop is very slow and hanging. Please raise a support ticket.", AUTHOR_EMP_ID),
            ("How do I set up MFA?", "How do I set up MFA on my phone?", None),
            ("I can't access the CRM system", "I can't access the CRM system. Getting a 403 error.", None),
            ("Register a new employee", "I need to register a new employee in the system.", None),
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
    st.caption("View all rows in DB. Use delete mode to select and remove specific rows.")

    employees_count, tickets_count = _db_counts()
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Employees", employees_count)
    with c2:
        st.metric("Tickets", tickets_count)

    table_name = st.selectbox(
        "Select table",
        ["employees", "tickets"],
        key="db_admin_table",
    )
    rows = _fetch_db_rows(table_name)
    st.caption(f"Rows in `{table_name}`: {len(rows)}")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    if mode == "view":
        st.info("Viewing mode active. Click **🗑️ Delete DB Rows** in sidebar to select and delete specific rows.")
        return

    id_field = "employee_id" if table_name == "employees" else "ticket_id"
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

    db_msg = st.session_state.get("db_admin_message")
    if db_msg:
        level, text = db_msg
        if level == "success":
            st.success(text)
        else:
            st.error(text)


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
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

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


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    init_session_state()
    ensure_db()
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
