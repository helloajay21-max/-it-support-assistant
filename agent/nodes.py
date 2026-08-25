"""
Graph nodes for the IT Support Assistant LangGraph workflow.
Each node represents a processing step in the agent pipeline.
"""

import json
import os
import re
import secrets
import smtplib
import ssl
import string
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from agent.state import AgentState
from tools.knowledge_search import knowledge_search
from tools.ticket_creation import ticket_creation
from tools.ticket_lookup import ticket_lookup
from tools.employee_registration import create_employee
from tools.employee_deletion import delete_employee
from data.init_db import get_db_connection
from utils.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# LLM Factory — supports both Azure OpenAI and standard OpenAI
# ------------------------------------------------------------------

def _build_llm() -> Any:
    """
    Build the LLM client based on environment configuration.
    Prefers Azure OpenAI if AZURE_OPENAI_ENDPOINT is set, else uses OpenAI.
    """
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_endpoint:
        logger.info("Using Azure OpenAI")
        return AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            temperature=0.2,
            max_tokens=1500,
        )
    else:
        logger.info("Using OpenAI")
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.2,
            max_tokens=1500,
        )


_llm = None

def get_llm():
    """Lazily initialize and return the LLM instance."""
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm


def _is_affirmative(text: str) -> bool:
    """Return True when text clearly expresses confirmation."""
    lowered = (text or "").lower()
    phrases = ["yes", "confirm", "confirmed", "sure", "ok", "okay", "proceed", "create", "go ahead", "do it"]
    return any(re.search(rf"\b{re.escape(p)}\b", lowered) for p in phrases)


def _is_negative(text: str) -> bool:
    """Return True when text clearly expresses cancellation/decline."""
    lowered = (text or "").lower()
    phrases = ["no", "cancel", "stop", "don't", "do not", "not now", "abort"]
    return any(re.search(rf"\b{re.escape(p)}\b", lowered) for p in phrases)


def _employee_profile(employee_id: str) -> dict:
    """Fetch basic employee profile for contextual responses."""
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


def _is_recent_employee(profile: dict, days: int = 7) -> bool:
    """Return True if employee profile was created recently."""
    if not profile or not profile.get("created_at"):
        return False
    try:
        created_at = datetime.fromisoformat(str(profile["created_at"]))
        return created_at >= datetime.now() - timedelta(days=days)
    except Exception:
        return False


def _is_valid_email(email: str) -> bool:
    """Simple email format validation for dispatch checks."""
    if not email:
        return False
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email.strip()))


def _generate_temp_password(length: int = 14) -> str:
    """Generate a strong temporary password for first-time VPN access."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    pwd = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase),
           secrets.choice(string.digits), secrets.choice("!@#$%^&*")]
    pwd.extend(secrets.choice(alphabet) for _ in range(max(0, length - 4)))
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def _smtp_settings() -> dict:
    """Read SMTP settings from environment variables."""
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_email": os.getenv("SMTP_FROM_EMAIL", "").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes"),
    }


def _send_email(to_email: str, subject: str, body: str, admin_email: str | None = None) -> tuple[bool, str]:
    """Send an email via SMTP using configured environment settings."""
    cfg = _smtp_settings()
    if not cfg["host"] or not cfg["from_email"]:
        return False, "SMTP not configured (SMTP_HOST/SMTP_FROM_EMAIL missing)"

    msg = EmailMessage()
    msg["From"] = cfg["from_email"]
    msg["To"] = to_email
    if admin_email and admin_email.strip().lower() != to_email.strip().lower():
        msg["Cc"] = admin_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=25) as server:
            if cfg["use_tls"]:
                server.starttls(context=ssl.create_default_context())
            if cfg["username"]:
                server.login(cfg["username"], cfg["password"])
            server.send_message(msg)
        return True, "Sent"
    except Exception as exc:
        logger.error("SMTP send failed to %s: %s", to_email, exc)
        return False, f"SMTP send failed: {exc}"


def _queue_vpn_email_dispatches(employee_id: str, employee_email: str, employee_name: str = "Employee") -> tuple[bool, str]:
    """
    Send and log both first-time setup and reset-password emails for a valid employee email.
    Persists outcome in DB log (Sent/Failed) for operational visibility.
    """
    if not employee_id or not _is_valid_email(employee_email):
        return False, "Email validation failed"

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        normalized_email = employee_email.strip().lower()
        admin_email = os.getenv("ADMIN_EMAIL", "helloajay21@gmail.com").strip().lower()
        reset_base = os.getenv("VPN_RESET_BASE_URL", "https://selfservice.techcorp.com/reset-vpn")
        reset_token = secrets.token_urlsafe(20)
        reset_link = f"{reset_base}?employee_id={employee_id}&token={reset_token}"
        temp_password = _generate_temp_password()

        first_time_subject = f"TechCorp VPN First-Time Setup - {employee_id}"
        first_time_body = (
            f"Hello {employee_name},\n\n"
            f"Your first-time VPN setup request is approved.\n\n"
            f"Employee ID: {employee_id}\n"
            f"Temporary VPN Password: {temp_password}\n"
            f"Activation / Reset Link: {reset_link}\n\n"
            f"Next steps:\n"
            f"1. Open Cisco AnyConnect\n"
            f"2. Login with your Employee ID and temporary password\n"
            f"3. Set your permanent password when prompted\n\n"
            f"If you face issues, reply to this email or contact IT Helpdesk.\n"
        )
        reset_subject = f"TechCorp VPN Password Reset - {employee_id}"
        reset_body = (
            f"Hello {employee_name},\n\n"
            f"Use the link below to reset your VPN password:\n"
            f"{reset_link}\n\n"
            f"This link expires in 30 minutes.\n"
            f"If you did not request this, contact IT Helpdesk immediately.\n"
        )

        sent_ok_1, msg_1 = _send_email(normalized_email, first_time_subject, first_time_body, admin_email)
        sent_ok_2, msg_2 = _send_email(normalized_email, reset_subject, reset_body, admin_email)

        rows = [
            (employee_id, normalized_email, "VPN_FIRST_TIME_SETUP", "email", "Sent" if sent_ok_1 else "Failed", now, msg_1),
            (employee_id, normalized_email, "VPN_PASSWORD_RESET", "email", "Sent" if sent_ok_2 else "Failed", now, msg_2),
        ]
        cursor.executemany(
            """
            INSERT INTO email_dispatch_log
            (employee_id, employee_email, dispatch_type, channel, status, requested_at, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()
        if sent_ok_1 and sent_ok_2:
            return True, "Sent first-time setup + reset password emails"
        return False, f"Email dispatch partial/failed: first-time={msg_1}; reset={msg_2}"
    except Exception as exc:
        logger.error("Failed to queue VPN email dispatches: %s", exc)
        return False, "Dispatch queue failed"


# ------------------------------------------------------------------
# System Prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI IT Support Assistant for TechCorp, helping employees resolve IT issues.

Your capabilities:
1. **Knowledge Search** – Answer how-to questions and provide troubleshooting guidance from the IT knowledge base.
2. **Ticket Lookup** – Check the status of existing IT support tickets.
3. **Ticket Creation** – Create new IT support tickets.
4. **Employee Registration** – Register a new employee so they can access IT services and raise tickets.
5. **Employee Deletion** – Deactivate or permanently delete employee records.

Guidelines:
- Be professional, friendly, and concise.
- Always validate employee ID before performing ticket operations.
- Employee IDs follow the format: EMP followed by 4+ digits (e.g., EMP1024).
- Do NOT invent ticket IDs, employee info, or system status.
- If you lack information, ask the user clearly.
- For ticket creation, always confirm details with the user before creating.
- For employee registration, collect name, email, department, and manager name before confirming.
- For employee deletion, always confirm scope (deactivate vs hard delete).
- Distinguish clearly between retrieved data and your own suggestions.
- Handle errors gracefully and provide helpful alternatives.

When detecting intent, classify as:
- knowledge_search: user asks how to do something, wants troubleshooting help, or asks about IT policies
- ticket_lookup: user wants to check ticket status or view their tickets
- ticket_creation: user wants to raise/create/log a new support ticket
- employee_registration: user wants to register/onboard/add a new employee to the system
- employee_deletion: user wants to deactivate/delete/remove an employee record
- general: general greeting, thank you, or out-of-scope question
"""


# ------------------------------------------------------------------
# Node Implementations
# ------------------------------------------------------------------

def intent_node(state: AgentState) -> dict:
    """
    Analyzes the latest user message and determines intent.
    Also extracts employee ID if present in the message.
    When mid-conversation info collection is in progress, the existing intent
    is preserved so routing stays on the correct tool node.
    """
    logger.info("Intent node executing")

    last_human_message = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    if not last_human_message:
        return {"intent": "general", "turn_count": state.turn_count + 1}

    # Extract employee ID from message if not already known
    employee_id = state.employee_id
    if not employee_id:
        match = re.search(r"\bEMP\d{4,}\b", last_human_message, re.IGNORECASE)
        if match:
            employee_id = match.group(0).upper()
            logger.info("Extracted employee ID from message: %s", employee_id)

    # ── Preserve intent during multi-turn info collection ─────────────────────
    # When we are mid-flow (awaiting_info=True), the user's short answer
    # (e.g. "John Doe", "IT") would be mis-classified as "general" by the LLM.
    # Returning only turn_count (and any extracted employee_id) keeps the stored
    # intent intact so the router can continue the current workflow.
    if state.awaiting_info and state.awaiting_field:
        logger.info(
            "Mid-collection flow detected (field=%s, intent=%s) — preserving intent",
            state.awaiting_field, state.intent
        )
        updates: dict = {"turn_count": state.turn_count + 1}
        if employee_id:
            updates["employee_id"] = employee_id
        return updates

    # Build context for intent detection
    recent_messages = state.messages[-6:]  # Last 3 turns
    intent_prompt = f"""Analyze this IT support request and classify the intent.

Recent conversation:
{chr(10).join([f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}" for m in recent_messages])}

Latest message: "{last_human_message}"

Classify the intent as exactly ONE of:
- knowledge_search: user wants IT help/instructions/troubleshooting
- ticket_lookup: user wants to check ticket status
- ticket_creation: user wants to create/raise a new ticket
- employee_registration: user wants to register/onboard/add a new employee
- employee_deletion: user wants to delete/deactivate/remove an employee
- general: greeting, thanks, or unrelated to IT support

Also extract if mentioned:
- employee_id: format EMP followed by digits
- ticket_id: format TKT-YYYY-NNN
- issue_category: VPN/Laptop/Email/Software/Hardware/Network/Password/Access/Printer/MFA/Security/Account/Other

Respond in JSON format only:
{{"intent": "...", "employee_id": "...", "ticket_id": "...", "issue_summary": "..."}}
"""

    try:
        response = get_llm().invoke([HumanMessage(content=intent_prompt)])
        raw = response.content.strip()

        # Parse JSON from response
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            intent = parsed.get("intent", "general")
            extracted_emp_id = parsed.get("employee_id", "")
            if extracted_emp_id and re.match(r"^EMP\d{4,}$", extracted_emp_id, re.IGNORECASE):
                employee_id = extracted_emp_id.upper()
        else:
            intent = "general"

    except Exception as e:
        logger.error("Intent detection error: %s", e)
        intent = "general"

    logger.info("Detected intent: %s, employee_id: %s", intent, employee_id)

    updates = {
        "intent": intent,
        "turn_count": state.turn_count + 1,
    }
    if employee_id:
        updates["employee_id"] = employee_id

    return updates


def collect_info_node(state: AgentState) -> dict:
    """
    Handles multi-turn information collection.
    Processes user answers to previous questions and updates pending state.
    """
    logger.info("Collect info node - awaiting field: %s", state.awaiting_field)

    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    updates = {}
    field = state.awaiting_field

    if field == "employee_id":
        match = re.search(r"\bEMP\d{4,}\b", last_human_message, re.IGNORECASE)
        if match:
            updates["employee_id"] = match.group(0).upper()
            updates["awaiting_info"] = False
            updates["awaiting_field"] = None
        else:
            # Still waiting for valid employee ID
            response = AIMessage(content="I didn't catch a valid employee ID. Please provide your employee ID in the format **EMP** followed by digits (e.g., EMP1024).")
            return {"messages": [response]}

    elif field == "description":
        if len(last_human_message.strip()) >= 10:
            pending = state.pending_ticket or {}
            pending["description"] = last_human_message.strip()
            updates["pending_ticket"] = pending
            updates["awaiting_info"] = False
            updates["awaiting_field"] = None
        else:
            response = AIMessage(content="Please provide a more detailed description of the issue (at least 10 characters).")
            return {"messages": [response]}

    elif field == "confirmation":
        affirmative = _is_affirmative(last_human_message)
        if affirmative:
            updates["awaiting_info"] = False
            updates["awaiting_field"] = None
            updates["intent"] = "ticket_creation"
        else:
            updates["awaiting_info"] = False
            updates["awaiting_field"] = None
            updates["pending_ticket"] = None
            updates["intent"] = "general"
            response = AIMessage(content="Understood, ticket creation has been cancelled. Is there anything else I can help you with?")
            return {"messages": [response], **updates}

    return updates


def knowledge_search_node(state: AgentState) -> dict:
    """
    Executes knowledge search with issue-triage state handling.
    For issue statements (e.g., "I have a VPN issue"), we collect employee ID,
    then offer ticket lookup before giving KB troubleshooting.
    """
    logger.info("Knowledge search node executing")

    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    pending_triage = dict(state.pending_triage) if state.pending_triage else {}
    lowered = last_human_message.lower()

    # Heuristic: this is an issue report (not a pure "how to ..." request)
    issue_report = any(k in lowered for k in [
        "issue", "problem", "not working", "can't", "cannot", "error", "failing", "slow", "hanging"
    ])
    vpn_related = "vpn" in lowered
    likely_troubleshooting_flow = issue_report and vpn_related

    # Step A: handle follow-up after asking employee ID
    if state.awaiting_field == "triage_employee_id":
        if not state.employee_id:
            return {
                "messages": [AIMessage(content="Please provide a valid employee ID in format **EMP####** (e.g., EMP1024).")],
                "awaiting_info": True,
                "awaiting_field": "triage_employee_id",
                "intent": "knowledge_search",
                "pending_triage": pending_triage,
                "tool_output": None,
            }

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM employees WHERE employee_id = ?", (state.employee_id,))
            row = cursor.fetchone()
            conn.close()
        except Exception:
            row = None

        if row:
            emp_name = row["name"]
            return {
                "messages": [AIMessage(content=(
                    f"I found your profile, **{emp_name} ({state.employee_id})**. "
                    f"Would you like me to check your existing tickets first? (**Yes / No**)"
                ))],
                "employee_name": emp_name,
                "awaiting_info": True,
                "awaiting_field": "triage_ticket_check",
                "intent": "knowledge_search",
                "pending_triage": pending_triage,
                "tool_output": None,
            }

        # Employee not found: continue with KB guidance but mention registration path
        pending_triage["employee_id"] = state.employee_id
        return {
            "messages": [AIMessage(content=(
                f"I couldn’t find **{state.employee_id}** in the employee database yet. "
                f"I can still help troubleshoot the VPN issue now, and we can register this employee if needed."
            ))],
            "awaiting_info": False,
            "awaiting_field": None,
            "intent": "knowledge_search",
            "pending_triage": pending_triage,
            "tool_output": None,
        }

    # Step B: after asking "check existing tickets?"
    if state.awaiting_field == "triage_ticket_check":
        affirmative = _is_affirmative(lowered) or "check tickets" in lowered
        query_for_kb = pending_triage.get("issue_query", last_human_message)

        if affirmative and state.employee_id:
            try:
                lookup_result = ticket_lookup.invoke({"employee_id": state.employee_id})
            except Exception as e:
                logger.error("Triage ticket lookup error: %s", e)
                lookup_result = "Error: Could not check existing tickets right now."

            return {
                "tool_output": lookup_result,
                "intent": "ticket_lookup",  # preserve raw lookup formatting path
                "awaiting_info": False,
                "awaiting_field": None,
                "pending_triage": None,
            }

        # User said no -> proceed to KB troubleshooting for the original issue query
        try:
            kb_result = knowledge_search.invoke({"query": query_for_kb})
        except Exception as e:
            logger.error("Knowledge search tool error after triage opt-out: %s", e)
            kb_result = "Error: Knowledge search tool encountered an issue. Please try again."
        return {
            "tool_output": kb_result,
            "intent": "knowledge_search",
            "awaiting_info": False,
            "awaiting_field": None,
            "pending_triage": None,
        }

    # Step C: start triage flow for issue statement
    if likely_troubleshooting_flow and not state.employee_id:
        return {
            "messages": [AIMessage(content=(
                "I can help with your VPN issue. First, what is your **employee ID** "
                "(e.g., EMP1024)?"
            ))],
            "awaiting_info": True,
            "awaiting_field": "triage_employee_id",
            "intent": "knowledge_search",
            "pending_triage": {"issue_query": last_human_message, "topic": "vpn"},
            "tool_output": None,
        }

    # Step D: if employee ID already known, offer ticket check first
    if likely_troubleshooting_flow and state.employee_id:
        return {
            "messages": [AIMessage(content=(
                f"I can help with your VPN issue. Would you like me to first check existing "
                f"tickets for **{state.employee_id}**? (**Yes / No**)"
            ))],
            "awaiting_info": True,
            "awaiting_field": "triage_ticket_check",
            "intent": "knowledge_search",
            "pending_triage": {"issue_query": last_human_message, "topic": "vpn"},
            "tool_output": None,
        }

    # Step E: First-time VPN setup flow for new employees
    first_time_words = ["first time", "new employee", "new joiner", "setup vpn", "set up vpn", "vpn setup", "initial setup"]
    is_first_time_request = vpn_related and any(w in lowered for w in first_time_words)
    profile = _employee_profile(state.employee_id) if state.employee_id else {}
    is_recent_new_employee = vpn_related and state.employee_id and _is_recent_employee(profile, days=14)

    if is_first_time_request or is_recent_new_employee:
        if not state.employee_id:
            return {
                "messages": [AIMessage(content=(
                    "I can help with first-time VPN onboarding. Please share your **employee ID** "
                    "(e.g., EMP1024) so I can check your profile and guide the exact steps."
                ))],
                "awaiting_info": True,
                "awaiting_field": "triage_employee_id",
                "intent": "knowledge_search",
                "pending_triage": {"issue_query": last_human_message, "topic": "vpn_onboarding"},
                "tool_output": None,
            }

        emp_name = profile.get("name", state.employee_name or "Employee")
        mgr = profile.get("manager_name", "your manager")
        email = profile.get("email", "your registered work email")
        dispatch_ok, dispatch_msg = _queue_vpn_email_dispatches(state.employee_id, email, emp_name)
        dispatch_note = (
            f"✅ Sent **first-time setup** and **password reset** emails to **{email}**."
            if dispatch_ok
            else f"⚠️ Could not send VPN emails: {dispatch_msg}."
        )
        onboarding_msg = (
            f"🔐 **First-Time VPN Setup for {emp_name} ({state.employee_id})**\n\n"
            f"Since this is first-time access, use **onboarding activation**, not password reset.\n\n"
            f"1. **Manager approval check**\n"
            f"   - Reporting manager on file: **{mgr}**\n"
            f"2. **VPN access provisioning**\n"
            f"   - IT creates your VPN profile and sends an activation email to **{email}**.\n"
            f"3. **Temporary credentials (secure delivery)**\n"
            f"   - For security, temporary VPN password is **not shown in chat**.\n"
            f"   - It is sent via secure channel (activation link / onboarding mail).\n"
            f"4. **Client setup**\n"
            f"   - Install/open Cisco AnyConnect.\n"
            f"   - Use your employee ID and temporary credentials.\n"
            f"5. **First login completion**\n"
            f"   - Set a new permanent password and reconnect.\n\n"
            f"{dispatch_note}\n\n"
            f"📌 If you did not receive activation credentials yet, say:\n"
            f"**'Create VPN onboarding ticket for {state.employee_id}'** and I’ll raise it."
        )
        return {
            "tool_output": onboarding_msg,
            "intent": "knowledge_search",
            "awaiting_info": False,
            "awaiting_field": None,
            "pending_triage": None,
        }

    try:
        result = knowledge_search.invoke({"query": last_human_message})
        if vpn_related and state.employee_id:
            profile = _employee_profile(state.employee_id)
            email = profile.get("email", "")
            dispatch_ok, dispatch_msg = _queue_vpn_email_dispatches(
                state.employee_id,
                email,
                profile.get("name", state.employee_name or "Employee"),
            )
            if dispatch_ok:
                result += (
                    f"\n\n---\n📧 **Dispatch Update:** "
                    f"Sent both first-time VPN setup and password-reset emails to **{email}**."
                )
            else:
                result += (
                    f"\n\n---\n⚠️ **Dispatch Update:** Could not send VPN emails ({dispatch_msg})."
                )
        logger.info("Knowledge search completed successfully")
    except Exception as e:
        logger.error("Knowledge search tool error: %s", e)
        result = "Error: Knowledge search tool encountered an issue. Please try again."

    return {"tool_output": result}


def ticket_lookup_node(state: AgentState) -> dict:
    """
    Executes the ticket lookup tool.
    Ensures employee ID is available before proceeding.
    """
    logger.info("Ticket lookup node executing")

    if not state.employee_id:
        response = AIMessage(content="To look up your tickets, I need your **employee ID** first. Please provide it (e.g., EMP1024).")
        return {
            "messages": [response],
            "awaiting_info": True,
            "awaiting_field": "employee_id",
            "intent": "ticket_lookup",
            "tool_output": None
        }

    # Check if user mentioned a specific ticket ID
    ticket_id = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            match = re.search(r"\bTKT-\d{4}-\d{3,}\b", msg.content, re.IGNORECASE)
            if match:
                ticket_id = match.group(0).upper()
            break

    try:
        params = {"employee_id": state.employee_id}
        if ticket_id:
            params["ticket_id"] = ticket_id
        result = ticket_lookup.invoke(params)
        logger.info("Ticket lookup completed for: %s", state.employee_id)
    except Exception as e:
        logger.error("Ticket lookup tool error: %s", e)
        result = "Error: Ticket lookup encountered an issue. Please try again."

    return {"tool_output": result}


def _employee_in_db(employee_id: str) -> bool:
    """Return True if the employee_id exists in the employees table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception as exc:
        logger.warning("Could not check employee in DB: %s — allowing ticket creation", exc)
        return True  # On DB error, don't block ticket creation


def ticket_creation_node(state: AgentState) -> dict:
    """
    Orchestrates ticket creation with multi-step validation.
    If the employee ID is not found in the database, automatically triggers
    an inline registration sub-flow before creating the ticket — providing
    a seamless end-to-end experience.
    """
    logger.info("Ticket creation node executing (awaiting_field=%s)", state.awaiting_field)

    # ── Get the last user message ─────────────────────────────────────────────
    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    # Work on a mutable copy of the pending ticket dict
    pending = dict(state.pending_ticket) if state.pending_ticket else {}
    field = state.awaiting_field

    # ── Handle ticket confirmation response explicitly (Yes/No) ────────────────
    if field == "confirmation":
        lowered = last_human_message.lower()
        affirmative = _is_affirmative(lowered)
        negative = _is_negative(lowered)

        if affirmative:
            pending["confirmed"] = True
        elif negative:
            wants_register = any(w in lowered for w in ["register", "new employee", "onboard", "create employee"])
            if wants_register:
                return {
                    "messages": [AIMessage(content=(
                        "Understood — ticket creation has been cancelled.\n\n"
                        "Let's register a new employee first. Please share details in this format:\n"
                        "**Name, Email, Department, Manager Name**\n\n"
                        "Example: `Ajay Sinha, ajay.sinha@techcorp.com, HR, Carol Davis`"
                    ))],
                    "pending_ticket": None,
                    "pending_employee": {},
                    "awaiting_info": True,
                    "awaiting_field": "emp_name",
                    "intent": "employee_registration",
                    "tool_output": None,
                }

            return {
                "messages": [AIMessage(content="Understood, ticket creation has been cancelled. If you want, I can help register a new employee first.")],
                "pending_ticket": None,
                "awaiting_info": False,
                "awaiting_field": None,
                "intent": "general",
                "tool_output": None,
            }
        else:
            return {
                "messages": [AIMessage(content="Please reply **Yes** to create the ticket or **No** to cancel.")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "confirmation",
                "intent": "ticket_creation",
                "tool_output": None,
            }

    # ── Collect answers for the inline auto-registration sub-flow ─────────────
    if field == "new_emp_name":
        val = last_human_message.strip()
        if len(val) >= 2:
            pending.setdefault("emp_reg", {})["name"] = val
        else:
            return {
                "messages": [AIMessage(content="Please enter a valid full name (at least 2 characters).")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_name",
                "intent": "ticket_creation",
                "tool_output": None,
            }

    elif field == "new_emp_email":
        val = last_human_message.strip()
        if re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", val):
            pending.setdefault("emp_reg", {})["email"] = val
        else:
            return {
                "messages": [AIMessage(content=f"'{val}' doesn't look like a valid email. Please provide your work email (e.g. `name@techcorp.com`).")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_email",
                "intent": "ticket_creation",
                "tool_output": None,
            }

    elif field == "new_emp_dept":
        val = last_human_message.strip()
        if len(val) >= 2:
            pending.setdefault("emp_reg", {})["department"] = val
        else:
            return {
                "messages": [AIMessage(content="Please provide your department name (e.g. Engineering, IT, Finance, HR, Sales).")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_dept",
                "intent": "ticket_creation",
                "tool_output": None,
            }

    elif field == "new_emp_manager":
        val = last_human_message.strip()
        if len(val) >= 2:
            pending.setdefault("emp_reg", {})["manager_name"] = val
        else:
            return {
                "messages": [AIMessage(content="Please provide your manager's full name (e.g. Carol Davis).")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_manager",
                "intent": "ticket_creation",
                "tool_output": None,
            }

    # ── Step 1: Need employee ID ──────────────────────────────────────────────
    if not state.employee_id:
        lowered = last_human_message.lower()
        if any(w in lowered for w in ["register new employee", "register employee", "new employee", "onboard employee"]):
            return {
                "messages": [AIMessage(content=(
                    "Sure — let's register the new employee first.\n\n"
                    "Please share details in this format:\n"
                    "**Name, Email, Department, Manager Name**\n\n"
                    "Example: `Ajay Sinha, ajay.sinha@techcorp.com, HR, Carol Davis`"
                ))],
                "pending_ticket": None,
                "pending_employee": {},
                "awaiting_info": True,
                "awaiting_field": "emp_name",
                "intent": "employee_registration",
                "tool_output": None,
            }

        response = AIMessage(content=(
            "I'd be happy to create a support ticket for you!\n\n"
            "Please provide your **employee ID** (e.g., EMP1025).\n"
            "If you don't have one yet, say: **register new employee**."
        ))
        return {
            "messages": [response],
            "awaiting_info": True,
            "awaiting_field": "employee_id",
            "intent": "ticket_creation",
            "tool_output": None,
        }

    # ── Step 2: Gather issue details ──────────────────────────────────────────
    if not pending.get("title") or not pending.get("description"):
        extract_prompt = f"""Extract IT support ticket information from this message: "{last_human_message}"

Also considering recent conversation context.

Extract:
- title: Short issue title (max 80 chars)
- description: Detailed description
- category: One of VPN/Laptop/Email/Software/Hardware/Network/Password/Access/Printer/MFA/Security/Account/Other
- priority: One of Low/Medium/High/Critical (default: Medium)

If description is too short or unclear, set description to null.

Respond in JSON only: {{"title": "...", "description": "...", "category": "...", "priority": "..."}}
"""
        try:
            response = get_llm().invoke([HumanMessage(content=extract_prompt)])
            raw = response.content.strip()
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group(0))
                if extracted.get("title"):
                    pending["title"] = extracted["title"]
                if extracted.get("description") and len(extracted["description"]) >= 10:
                    pending["description"] = extracted["description"]
                if extracted.get("category"):
                    pending["category"] = extracted["category"]
                if extracted.get("priority"):
                    pending["priority"] = extracted["priority"]
        except Exception as e:
            logger.error("Ticket info extraction error: %s", e)

    # ── Step 3: Ask for missing description ───────────────────────────────────
    if not pending.get("description") or len(pending.get("description", "")) < 10:
        title_hint = f" regarding **{pending.get('title', 'your issue')}**" if pending.get("title") else ""
        response = AIMessage(content=f"To create a ticket{title_hint}, please describe the issue in more detail. What exactly is happening?")
        return {
            "messages": [response],
            "pending_ticket": pending,
            "awaiting_info": True,
            "awaiting_field": "description",
            "intent": "ticket_creation",
            "tool_output": None,
        }

    # ── Step 4: Confirm before creating ──────────────────────────────────────
    if not pending.get("confirmed"):
        confirm_msg = (
            f"Here are the details for your new support ticket:\n\n"
            f"👤 **Employee ID:** {state.employee_id}\n"
            f"📋 **Title:** {pending.get('title', 'N/A')}\n"
            f"🏷️ **Category:** {pending.get('category', 'Other')}\n"
            f"⚡ **Priority:** {pending.get('priority', 'Medium')}\n"
            f"📝 **Description:** {pending.get('description', 'N/A')}\n\n"
            f"Shall I create this ticket? (**Yes / No**)"
        )
        return {
            "messages": [AIMessage(content=confirm_msg)],
            "pending_ticket": pending,
            "awaiting_info": True,
            "awaiting_field": "confirmation",
            "intent": "ticket_creation",
            "tool_output": None,
        }

    # ── Step 4.5: Auto-register if employee not in DB ────────────────────────
    #    Triggered after user confirms ticket details; transparently registers the
    #    employee then continues straight to ticket creation.
    if not _employee_in_db(state.employee_id):
        reg = pending.get("emp_reg", {})

        if not reg.get("name"):
            response = AIMessage(content=(
                f"I'd love to create that ticket for you, but **{state.employee_id}** "
                f"isn't registered in the system yet.\n\n"
                f"No worries — let me register you right now! It'll only take a moment.\n\n"
                f"What is your **full name**?"
            ))
            return {
                "messages": [response],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_name",
                "intent": "ticket_creation",
                "tool_output": None,
            }

        if not reg.get("email"):
            return {
                "messages": [AIMessage(content=f"Thanks **{reg['name']}**! What is your **work email address**?")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_email",
                "intent": "ticket_creation",
                "tool_output": None,
            }

        if not reg.get("department"):
            return {
                "messages": [AIMessage(content=f"Almost done! Which **department** are you in?\n*(e.g. Engineering, IT, Finance, HR, Sales)*")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_dept",
                "intent": "ticket_creation",
                "tool_output": None,
            }

        if not reg.get("manager_name"):
            return {
                "messages": [AIMessage(content="Great. What is your **manager's full name**?")],
                "pending_ticket": pending,
                "awaiting_info": True,
                "awaiting_field": "new_emp_manager",
                "intent": "ticket_creation",
                "tool_output": None,
            }

        # All info collected — auto-register, preserving the provided employee_id
        logger.info("Auto-registering %s (%s) before ticket creation", state.employee_id, reg.get("name"))
        try:
            reg_result = create_employee.invoke({
                "name": reg["name"],
                "email": reg["email"],
                "department": reg["department"],
                "manager_name": reg["manager_name"],
                "employee_id": state.employee_id,
            })
        except Exception as exc:
            logger.error("Auto-registration error: %s", exc)
            reg_result = "❌ Registration failed"

        if "❌" in reg_result:
            # Surface the registration error and abort ticket creation
            return {
                "tool_output": reg_result + "\n\n⚠️ Ticket creation was not completed due to the registration issue above.",
                "pending_ticket": None,
                "awaiting_info": False,
                "awaiting_field": None,
            }

        logger.info("Auto-registration succeeded for %s", state.employee_id)
        pending["auto_reg_result"] = reg_result  # Carry result into final response

    # ── Step 5: Create the ticket ─────────────────────────────────────────────
    try:
        result = ticket_creation.invoke({
            "employee_id": state.employee_id,
            "title": pending.get("title", "IT Support Request"),
            "description": pending.get("description", ""),
            "category": pending.get("category", "Other"),
            "priority": pending.get("priority", "Medium"),
        })
        logger.info("Ticket creation completed for: %s", state.employee_id)

        # Prepend auto-registration success note if applicable
        if pending.get("auto_reg_result"):
            result = (
                f"✅ **Employee Registered & Ticket Created**\n\n"
                f"**Registration:**\n{pending['auto_reg_result']}\n\n"
                f"---\n\n"
                f"**Ticket:**\n{result}"
            )
    except Exception as e:
        logger.error("Ticket creation tool error: %s", e)
        result = "❌ Error: Failed to create ticket. Please try again or contact IT helpdesk."

    return {
        "tool_output": result,
        "pending_ticket": None,
        "awaiting_info": False,
        "awaiting_field": None,
    }


def employee_deletion_node(state: AgentState) -> dict:
    """
    Deactivate or hard-delete an employee from the database with confirmation.
    """
    logger.info("Employee deletion node executing (awaiting_field=%s)", state.awaiting_field)

    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    pending = dict(state.pending_delete) if state.pending_delete else {}
    field = state.awaiting_field

    # collect follow-up answers
    if field == "delete_employee_id":
        m = re.search(r"\bEMP\d{4,}\b", last_human_message, re.IGNORECASE)
        if not m:
            return {
                "messages": [AIMessage(content="Please provide a valid employee ID in format EMP####.")],
                "pending_delete": pending,
                "awaiting_info": True,
                "awaiting_field": "delete_employee_id",
                "intent": "employee_deletion",
            }
        pending["employee_id"] = m.group(0).upper()

    if field == "delete_mode":
        msg = last_human_message.lower()
        pending["hard_delete"] = any(k in msg for k in ["hard", "permanent", "purge", "delete tickets"])

    if field == "delete_confirmation":
        affirmative = _is_affirmative(last_human_message) or bool(re.search(r"\bdelete\b", (last_human_message or "").lower()))
        if not affirmative:
            return {
                "messages": [AIMessage(content="Understood, employee deletion was cancelled.")],
                "pending_delete": None,
                "awaiting_info": False,
                "awaiting_field": None,
                "intent": "general",
            }
        pending["confirmed"] = True

    # infer employee_id from current message if present
    if not pending.get("employee_id"):
        m = re.search(r"\bEMP\d{4,}\b", last_human_message, re.IGNORECASE)
        if m:
            pending["employee_id"] = m.group(0).upper()

    if not pending.get("employee_id"):
        return {
            "messages": [AIMessage(content="Please provide the employee ID you want to delete/deactivate (e.g., EMP1025).")],
            "pending_delete": pending,
            "awaiting_info": True,
            "awaiting_field": "delete_employee_id",
            "intent": "employee_deletion",
            "tool_output": None,
        }

    if "hard_delete" not in pending:
        return {
            "messages": [AIMessage(content=(
                f"For **{pending['employee_id']}**, should I do:\n"
                f"1) **Deactivate** (keeps tickets), or\n"
                f"2) **Hard delete** (removes employee + all tickets)?\n\n"
                f"Reply with *deactivate* or *hard delete*."
            ))],
            "pending_delete": pending,
            "awaiting_info": True,
            "awaiting_field": "delete_mode",
            "intent": "employee_deletion",
            "tool_output": None,
        }

    if not pending.get("confirmed"):
        action = "HARD DELETE employee + tickets" if pending["hard_delete"] else "DEACTIVATE employee (keep tickets)"
        return {
            "messages": [AIMessage(content=(
                f"Please confirm: **{action}** for `{pending['employee_id']}`?\n\n"
                f"Reply **Yes** to continue or **No** to cancel."
            ))],
            "pending_delete": pending,
            "awaiting_info": True,
            "awaiting_field": "delete_confirmation",
            "intent": "employee_deletion",
            "tool_output": None,
        }

    try:
        result = delete_employee.invoke({
            "employee_id": pending["employee_id"],
            "hard_delete": bool(pending.get("hard_delete", False)),
        })
    except Exception as exc:
        logger.error("employee_deletion tool error: %s", exc)
        result = "❌ Failed to process employee deletion request."

    return {
        "tool_output": result,
        "pending_delete": None,
        "awaiting_info": False,
        "awaiting_field": None,
    }


def response_node(state: AgentState) -> dict:
    """
    Generates a final user-friendly response using the LLM.
    Incorporates tool output and conversation context.
    """
    logger.info("Response node executing")

    # For operational tool outputs, preserve exact structured result from tools.
    # This avoids LLM rewording that can misreport create/delete outcomes.
    if state.intent in {"knowledge_search", "ticket_lookup", "ticket_creation", "employee_registration", "employee_deletion"} and state.tool_output:
        return {"messages": [AIMessage(content=state.tool_output)], "tool_output": None}

    # If no tool was called (general intent), generate direct response
    if not state.tool_output:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state.messages[-10:])
        try:
            ai_response = get_llm().invoke(messages)
            return {"messages": [AIMessage(content=ai_response.content)], "tool_output": None}
        except Exception as e:
            logger.error("LLM response error: %s", e)
            return {"messages": [AIMessage(content="I'm sorry, I encountered an error processing your request. Please try again.")], "tool_output": None}

    # Generate response incorporating tool output
    tool_output = state.tool_output
    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    response_prompt = f"""You are an IT Support Assistant. Based on the tool result below, provide a clear and helpful response to the user.

User's request: "{last_human_message}"

Tool Result:
{tool_output}

Instructions:
- Present the information clearly and professionally.
- If it's a knowledge base result, summarize the key steps and offer further help.
- If it's ticket information, present it clearly and ask if there's anything else needed.
- If it's a ticket creation result, confirm the creation warmly and mention next steps.
- Keep response concise but complete. Use markdown formatting.
- End with an offer to help further if appropriate.
"""

    try:
        ai_response = get_llm().invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=response_prompt)
        ])
        final_response = ai_response.content
    except Exception as e:
        logger.error("Response generation error: %s", e)
        final_response = tool_output  # Fall back to raw tool output

    return {
        "messages": [AIMessage(content=final_response)],
        "tool_output": None
    }


# ── Employee Registration Node ────────────────────────────────────────────────

def employee_registration_node(state: AgentState) -> dict:
    """
    Orchestrates new employee registration with step-by-step validation.

    Collection order:
      1. name  → 2. email  → 3. department → 4. manager_name → 5. role (optional / defaults)
      → 6. confirm  → 7. create via create_employee tool
    """
    logger.info("Employee registration node executing (awaiting_field=%s)", state.awaiting_field)

    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    pending = dict(state.pending_employee) if state.pending_employee else {}

    # ── Collect answers from previous questions ────────────────────────────────
    field = state.awaiting_field

    if field == "emp_name":
        name_val = last_human_message.strip()

        # Support one-line input: "Name, Email, Department, Manager[, Role]"
        parts = [p.strip() for p in name_val.split(",")]
        if len(parts) >= 3 and re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", parts[1]):
            pending["name"] = parts[0]
            pending["email"] = parts[1]
            pending["department"] = parts[2]
            if len(parts) >= 4 and parts[3]:
                pending["manager_name"] = parts[3]
            if len(parts) >= 5 and parts[4]:
                pending["role"] = parts[4]
        elif len(name_val) >= 2:
            pending["name"] = name_val
        else:
            return {
                "messages": [AIMessage(content="Please provide a valid full name (at least 2 characters).")],
                "pending_employee": pending,
                "awaiting_info": True,
                "awaiting_field": "emp_name",
                "intent": "employee_registration",
            }

    elif field == "emp_email":
        import re as _re
        email_val = last_human_message.strip()
        if _re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email_val):
            pending["email"] = email_val
        else:
            return {
                "messages": [AIMessage(content=f"'{email_val}' doesn't look like a valid email. Please provide a valid work email address (e.g. `john.doe@techcorp.com`).")],
                "pending_employee": pending,
                "awaiting_info": True,
                "awaiting_field": "emp_email",
                "intent": "employee_registration",
            }

    elif field == "emp_department":
        dept_val = last_human_message.strip()
        if len(dept_val) >= 2:
            pending["department"] = dept_val
        else:
            return {
                "messages": [AIMessage(content="Please provide the department name (e.g. Engineering, IT, Finance, HR, Sales).")],
                "pending_employee": pending,
                "awaiting_info": True,
                "awaiting_field": "emp_department",
                "intent": "employee_registration",
            }

    elif field == "emp_manager":
        manager_val = last_human_message.strip()
        if len(manager_val) >= 2:
            pending["manager_name"] = manager_val
        else:
            return {
                "messages": [AIMessage(content="Please provide the reporting manager's full name (e.g. Carol Davis).")],
                "pending_employee": pending,
                "awaiting_info": True,
                "awaiting_field": "emp_manager",
                "intent": "employee_registration",
            }

    elif field == "emp_role":
        role_val = last_human_message.strip()
        pending["role"] = role_val if role_val else "Employee"

    elif field == "emp_confirmation":
        affirmative = _is_affirmative(last_human_message) or bool(re.search(r"\bregister\b", (last_human_message or "").lower()))
        if not affirmative:
            response = AIMessage(content="Understood — employee registration has been cancelled. Is there anything else I can help you with?")
            return {
                "messages": [response],
                "pending_employee": None,
                "awaiting_info": False,
                "awaiting_field": None,
                "intent": "general",
            }
        pending["confirmed"] = True

    # ── Try to extract fields from the original message if not yet collected ──
    if not pending.get("name") and field not in ("emp_name",):
        # Try LLM extraction from the initial message
        try:
            extract_prompt = (
                f'Extract employee registration details from: "{last_human_message}"\n'
                'Return JSON only: {"name": "...", "email": "...", "department": "...", "manager_name": "...", "role": "..."}\n'
                'Set null for any field not clearly mentioned.'
            )
            resp = get_llm().invoke([HumanMessage(content=extract_prompt)])
            raw = resp.content.strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                extracted = json.loads(m.group(0))
                for key in ("name", "email", "department", "manager_name", "role"):
                    if extracted.get(key) and not pending.get(key):
                        pending[key] = extracted[key]
        except Exception as exc:
            logger.warning("Could not extract employee details from message: %s", exc)

    # ── Step through collection ────────────────────────────────────────────────
    if not pending.get("name"):
        response = AIMessage(content="I'd be happy to register a new employee! Let's start with the basics.\n\nWhat is the **full name** of the new employee?")
        return {
            "messages": [response],
            "pending_employee": pending,
            "awaiting_info": True,
            "awaiting_field": "emp_name",
            "intent": "employee_registration",
            "tool_output": None,
        }

    if not pending.get("email"):
        response = AIMessage(content=f"Got it — **{pending['name']}**.\n\nWhat is their **work email address**?")
        return {
            "messages": [response],
            "pending_employee": pending,
            "awaiting_info": True,
            "awaiting_field": "emp_email",
            "intent": "employee_registration",
            "tool_output": None,
        }

    if not pending.get("department"):
        response = AIMessage(content=f"Thanks! Which **department** will **{pending['name']}** be joining?\n*(e.g. Engineering, IT, Finance, HR, Sales, Marketing, Operations)*")
        return {
            "messages": [response],
            "pending_employee": pending,
            "awaiting_info": True,
            "awaiting_field": "emp_department",
            "intent": "employee_registration",
            "tool_output": None,
        }

    if not pending.get("manager_name"):
        response = AIMessage(content=f"Who will be the **reporting manager** for **{pending['name']}**?")
        return {
            "messages": [response],
            "pending_employee": pending,
            "awaiting_info": True,
            "awaiting_field": "emp_manager",
            "intent": "employee_registration",
            "tool_output": None,
        }

    # Role is optional — default to "Employee" if not yet set
    if "role" not in pending:
        pending["role"] = "Employee"

    # ── Confirmation step ─────────────────────────────────────────────────────
    if not pending.get("confirmed"):
        confirm_msg = (
            f"Please confirm the details for the new employee:\n\n"
            f"  👤 **Name**        : {pending.get('name')}\n"
            f"  📧 **Email**       : {pending.get('email')}\n"
            f"  🏢 **Department**  : {pending.get('department')}\n"
            f"  👔 **Manager**     : {pending.get('manager_name')}\n"
            f"  💼 **Role**        : {pending.get('role', 'Employee')}\n\n"
            f"Shall I register this employee? (**Yes / No**)"
        )
        return {
            "messages": [AIMessage(content=confirm_msg)],
            "pending_employee": pending,
            "awaiting_info": True,
            "awaiting_field": "emp_confirmation",
            "intent": "employee_registration",
            "tool_output": None,
        }

    # ── Execute registration ───────────────────────────────────────────────────
    try:
        result = create_employee.invoke({
            "name": pending.get("name", ""),
            "email": pending.get("email", ""),
            "department": pending.get("department", ""),
            "manager_name": pending.get("manager_name", "N/A"),
            "role": pending.get("role", "Employee"),
        })
        logger.info("Employee registration completed: %s", pending.get("name"))
    except Exception as exc:
        logger.error("create_employee tool error: %s", exc)
        result = "❌ Error: Failed to register employee. Please try again or contact the system administrator."

    # Persist created employee identity in conversation state so subsequent
    # ticket actions use the newly created employee without asking again.
    created_emp_id = None
    if isinstance(result, str):
        m = re.search(r"\bEMP\d{4,}\b", result, re.IGNORECASE)
        if m:
            created_emp_id = m.group(0).upper()

    return {
        "tool_output": result,
        "employee_id": created_emp_id or state.employee_id,
        "employee_name": pending.get("name", state.employee_name),
        "pending_employee": None,
        "awaiting_info": False,
        "awaiting_field": None,
    }
