"""
Graph nodes for the IT Support Assistant LangGraph workflow.
Each node represents a processing step in the agent pipeline.
"""

import json
import os
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from agent.state import AgentState
from tools.knowledge_search import knowledge_search
from tools.ticket_creation import ticket_creation
from tools.ticket_lookup import ticket_lookup
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


# ------------------------------------------------------------------
# System Prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI IT Support Assistant for TechCorp, helping employees resolve IT issues.

Your capabilities:
1. **Knowledge Search** – Answer how-to questions and provide troubleshooting guidance from the IT knowledge base.
2. **Ticket Lookup** – Check the status of existing IT support tickets.
3. **Ticket Creation** – Create new IT support tickets.

Guidelines:
- Be professional, friendly, and concise.
- Always validate employee ID before performing ticket operations.
- Employee IDs follow the format: EMP followed by 4+ digits (e.g., EMP1024).
- Do NOT invent ticket IDs, employee info, or system status.
- If you lack information, ask the user clearly.
- For ticket creation, always confirm details with the user before creating.
- Distinguish clearly between retrieved data and your own suggestions.
- Handle errors gracefully and provide helpful alternatives.

When detecting intent, classify as:
- knowledge_search: user asks how to do something, wants troubleshooting help, or asks about IT policies
- ticket_lookup: user wants to check ticket status or view their tickets
- ticket_creation: user wants to raise/create/log a new support ticket
- general: general greeting, thank you, or out-of-scope question
"""


# ------------------------------------------------------------------
# Node Implementations
# ------------------------------------------------------------------

def intent_node(state: AgentState) -> dict:
    """
    Analyzes the latest user message and determines intent.
    Also extracts employee ID if present in the message.
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
        affirmative = any(word in last_human_message.lower() for word in ["yes", "y", "confirm", "sure", "ok", "proceed", "create", "go ahead"])
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
    Executes the knowledge search tool with the user's query.
    """
    logger.info("Knowledge search node executing")

    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    try:
        result = knowledge_search.invoke({"query": last_human_message})
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


def ticket_creation_node(state: AgentState) -> dict:
    """
    Orchestrates ticket creation with multi-step validation.
    Collects missing info before creating the ticket.
    """
    logger.info("Ticket creation node executing")

    # Step 1: Need employee ID
    if not state.employee_id:
        response = AIMessage(content="I'd be happy to create a support ticket for you! First, I'll need your **employee ID** (e.g., EMP1024). What is your employee ID?")
        return {
            "messages": [response],
            "awaiting_info": True,
            "awaiting_field": "employee_id",
            "intent": "ticket_creation",
            "tool_output": None
        }

    # Step 2: Gather issue details
    last_human_message = ""
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_human_message = msg.content
            break

    # Build pending ticket if not exists
    pending = state.pending_ticket or {}

    if not pending.get("title") or not pending.get("description"):
        # Use LLM to extract ticket details from conversation
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

    # Step 3: Ask for missing description
    if not pending.get("description") or len(pending.get("description", "")) < 10:
        title_hint = f" regarding **{pending.get('title', 'your issue')}**" if pending.get("title") else ""
        response = AIMessage(content=f"To create a ticket{title_hint}, please describe the issue in more detail. What exactly is happening?")
        return {
            "messages": [response],
            "pending_ticket": pending,
            "awaiting_info": True,
            "awaiting_field": "description",
            "intent": "ticket_creation",
            "tool_output": None
        }

    # Step 4: Confirm before creating (if not already confirmed)
    if not pending.get("confirmed"):
        pending["confirmed"] = True
        confirm_msg = (
            f"Here are the details for your new support ticket:\n\n"
            f"👤 **Employee ID:** {state.employee_id}\n"
            f"📋 **Title:** {pending.get('title', 'N/A')}\n"
            f"🏷️ **Category:** {pending.get('category', 'Other')}\n"
            f"⚡ **Priority:** {pending.get('priority', 'Medium')}\n"
            f"📝 **Description:** {pending.get('description', 'N/A')}\n\n"
            f"Shall I create this ticket? (Yes/No)"
        )
        response = AIMessage(content=confirm_msg)
        return {
            "messages": [response],
            "pending_ticket": pending,
            "awaiting_info": True,
            "awaiting_field": "confirmation",
            "intent": "ticket_creation",
            "tool_output": None
        }

    # Step 5: Create the ticket
    try:
        result = ticket_creation.invoke({
            "employee_id": state.employee_id,
            "title": pending.get("title", "IT Support Request"),
            "description": pending.get("description", ""),
            "category": pending.get("category", "Other"),
            "priority": pending.get("priority", "Medium")
        })
        logger.info("Ticket creation completed for: %s", state.employee_id)
    except Exception as e:
        logger.error("Ticket creation tool error: %s", e)
        result = "❌ Error: Failed to create ticket. Please try again or contact IT helpdesk."

    return {"tool_output": result, "pending_ticket": None, "awaiting_info": False, "awaiting_field": None}


def response_node(state: AgentState) -> dict:
    """
    Generates a final user-friendly response using the LLM.
    Incorporates tool output and conversation context.
    """
    logger.info("Response node executing")

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
