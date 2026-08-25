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

from data.init_db import init_db
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
def run_agent(user_input: str) -> Optional[str]:
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
            "employee_id": prior.employee_id,
            "employee_name": prior.employee_name,
            "intent": prior.intent,
            "pending_ticket": prior.pending_ticket,
            "pending_employee": prior.pending_employee,
            "awaiting_info": prior.awaiting_info,
            "awaiting_field": prior.awaiting_field,
            "tool_output": None,
            "turn_count": prior.turn_count,
        }
    else:
        input_state = {"messages": [new_message]}

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
def render_sidebar():
    """Render the sidebar with session info, tools, and quick actions."""
    with st.sidebar:
        st.markdown("## 🖥️ IT Support Assistant")
        st.markdown("*Powered by Agentic AI + LangGraph*")
        st.markdown(
            """
            <div class="author-card">
                <div class="label">Project Author</div>
                <div class="name">Ajay Kumar</div>
                <div class="email">helloajay21@gmail.com</div>
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
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Turns", st.session_state.turn_count)
        with col2:
            emp_id = (agent_state.employee_id if agent_state else None) or "—"
            st.metric("Employee", emp_id)

        if agent_state and agent_state.awaiting_info:
            st.warning(f"⏳ Awaiting: **{agent_state.awaiting_field}**")

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
        ]
        for icon, name, desc in tools_info:
            st.markdown(f"**{icon} {name}**  \n{desc}")

        st.divider()

        # ── Quick Prompts ──
        st.markdown("### 💬 Quick Prompts")
        quick_prompts = [
            "How do I reset my VPN password?",
            "What is the status of my tickets? (EMP1024)",
            "My laptop is very slow. Please raise a ticket.",
            "How do I set up MFA?",
            "I can't access the CRM system.",
            "Register a new employee",
        ]
        for prompt in quick_prompts:
            if st.button(prompt, key=f"qp_{prompt[:20]}", use_container_width=True):
                st.session_state["pending_quick_prompt"] = prompt
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

    # Display chat history
    chat_container = st.container()
    with chat_container:
        if not st.session_state.messages:
            st.markdown("""
            👋 **Welcome to TechCorp IT Support!**

            I'm your AI IT Support Assistant. I can help you with:
            - 🔍 **Troubleshooting** — Step-by-step guides for common IT issues
            - 🎫 **Ticket Status** — Check your existing support tickets
            - 📝 **Raise a Ticket** — Create a new IT support request
            - 👤 **Employee Registration** — Onboard a new employee into the system

            **Try asking:**
            - *"How do I reset my VPN password?"*
            - *"Check tickets for EMP1024"*
            - *"My laptop won't turn on, please raise a ticket"*
            - *"Register a new employee: Ajay Kumar, ajay@techcorp.com, IT department"*
            """)
        else:
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
                    st.markdown(msg["content"])

    # Handle quick prompt from sidebar
    pending_prompt = st.session_state.pop("pending_quick_prompt", None)

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
                response = run_agent(user_input)

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
