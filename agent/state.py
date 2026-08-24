"""
Agent State Definition for IT Support Assistant.
Defines the shared state that flows through the LangGraph workflow.
"""

from typing import Annotated, Optional
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """
    Shared state maintained across all nodes in the LangGraph workflow.
    Uses add_messages reducer to accumulate conversation history.
    """

    # Conversation messages — uses LangGraph's add_messages reducer
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    # Collected employee context across conversation turns
    employee_id: Optional[str] = None
    employee_name: Optional[str] = None

    # Current intent determined by the router
    intent: Optional[str] = None  # "knowledge_search" | "ticket_lookup" | "ticket_creation" | "general"

    # Pending ticket data being collected for ticket creation
    pending_ticket: Optional[dict] = None

    # Whether we're in multi-turn info collection mode
    awaiting_info: bool = False

    # What specific info we're waiting for from the user
    awaiting_field: Optional[str] = None  # "employee_id" | "description" | "priority" | "confirmation"

    # Raw output from the last tool call
    tool_output: Optional[str] = None

    # Number of conversation turns (for context management)
    turn_count: int = 0

    class Config:
        arbitrary_types_allowed = True
