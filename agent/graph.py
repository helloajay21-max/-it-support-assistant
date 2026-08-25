"""
LangGraph workflow definition for IT Support Assistant.
Orchestrates the full agentic pipeline with state, nodes, edges, and routing.
"""

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    intent_node,
    knowledge_search_node,
    response_node,
    ticket_creation_node,
    ticket_lookup_node,
    employee_registration_node,
)
from agent.state import AgentState
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Routing functions ────────────────────────────────────────────────────────

def route_from_intent(state: AgentState) -> str:
    """
    Combined router from intent_node.
    - If a previous turn left us awaiting user input, re-route to the correct tool
      node based on the stored intent (intent_node preserved it when awaiting_info).
    - Otherwise route by detected intent.
    """
    # Mid-conversation info collection: route to the correct tool
    if state.awaiting_info and state.awaiting_field:
        intent = state.intent or "general"
        if intent == "ticket_lookup":
            return "ticket_lookup_node"
        if intent == "ticket_creation":
            return "ticket_creation_node"
        if intent == "employee_registration":
            return "employee_registration_node"

    intent = state.intent or "general"
    if intent == "knowledge_search":
        return "knowledge_search_node"
    if intent == "ticket_lookup":
        return "ticket_lookup_node"
    if intent == "ticket_creation":
        return "ticket_creation_node"
    if intent == "employee_registration":
        return "employee_registration_node"
    return "response_node"


def route_after_tool(state: AgentState) -> str:
    """
    After a tool node executes:
    - If the node asked a clarifying question (awaiting_info=True), it already
      added an AIMessage; go directly to END so we don't double-respond.
    - If there is tool output to be formatted, go to response_node.
    - Otherwise (no output, no pending question) fall through to response_node
      for a graceful catch-all.
    """
    if state.awaiting_info:
        return END
    return "response_node"


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph():
    """
    Build and compile the LangGraph workflow.

    Architecture:
    ─────────────────────────────────────────────────────────────────
    START
      │
      ▼
    [intent_node]
      │  (route_from_intent)
      ├──► knowledge_search_node ──► (route_after_tool) ──► response_node ──► END
      ├──► ticket_lookup_node    ──► (route_after_tool) ──► response_node ──► END
      ├──► ticket_creation_node  ──► (route_after_tool) ──► response_node ──► END
      │         │ (if awaiting_info)                          ▲
      │         └──────────────────────────────────────► END  │
      └──► response_node ─────────────────────────────────────┘──► END
    ─────────────────────────────────────────────────────────────────
    """
    workflow = StateGraph(AgentState)

    # ── Register nodes ───────────────────────────────────
    workflow.add_node("intent_node", intent_node)
    workflow.add_node("knowledge_search_node", knowledge_search_node)
    workflow.add_node("ticket_lookup_node", ticket_lookup_node)
    workflow.add_node("ticket_creation_node", ticket_creation_node)
    workflow.add_node("employee_registration_node", employee_registration_node)
    workflow.add_node("response_node", response_node)

    # ── Entry point ──────────────────────────────────────
    workflow.add_edge(START, "intent_node")

    # ── Intent → tool routing ────────────────────────────
    workflow.add_conditional_edges(
        "intent_node",
        route_from_intent,
        {
            "knowledge_search_node": "knowledge_search_node",
            "ticket_lookup_node": "ticket_lookup_node",
            "ticket_creation_node": "ticket_creation_node",
            "employee_registration_node": "employee_registration_node",
            "response_node": "response_node",
        }
    )

    # ── Tool → response / END routing ────────────────────
    for tool_node in (
        "knowledge_search_node",
        "ticket_lookup_node",
        "ticket_creation_node",
        "employee_registration_node",
    ):
        workflow.add_conditional_edges(
            tool_node,
            route_after_tool,
            {
                "response_node": "response_node",
                END: END,
            }
        )

    # ── Response node → END ──────────────────────────────
    workflow.add_edge("response_node", END)

    compiled = workflow.compile()
    logger.info("LangGraph workflow compiled successfully")
    return compiled


# Singleton graph instance
_graph = None


def get_graph():
    """Return the compiled graph, initializing if needed."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
