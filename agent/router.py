"""
Conditional router for the LangGraph IT Support workflow.
Determines which node to execute next based on agent state.
"""

from agent.state import AgentState
from utils.logger import get_logger

logger = get_logger(__name__)


def route_after_intent(state: AgentState) -> str:
    """
    Routes to the appropriate tool node based on detected intent.

    Args:
        state: Current agent state with intent field populated.

    Returns:
        Name of the next node to execute.
    """
    intent = state.intent or "general"
    logger.debug("Routing based on intent: %s", intent)

    if intent == "knowledge_search":
        return "knowledge_search_node"
    elif intent == "ticket_lookup":
        return "ticket_lookup_node"
    elif intent == "ticket_creation":
        return "ticket_creation_node"
    else:
        return "response_node"


def route_after_tool(state: AgentState) -> str:
    """
    Routes after a tool has executed.
    Always goes to the response generation node.

    Args:
        state: Current agent state.

    Returns:
        Always returns 'response_node'.
    """
    return "response_node"


def should_collect_info(state: AgentState) -> str:
    """
    Determines whether we need to collect more info before proceeding.

    Args:
        state: Current agent state.

    Returns:
        'collect_info' if more info is needed, else 'route_intent'.
    """
    if state.awaiting_info and state.awaiting_field:
        logger.debug("Still awaiting field: %s", state.awaiting_field)
        return "collect_info_node"
    return "intent_node"
