"""
backend/agents/orchestrator.py
Orchestrator agent factory.

build_agent(creds) constructs a per-request Strands agent. Per-request rather
than a module singleton because tools close over user-specific Google
credentials.

The system prompt describes the role, not today's tool list, so adding tools
doesn't require rewriting it.
"""

from strands import Agent
from google.oauth2.credentials import Credentials
from backend.core.config import settings
from backend.agents.availability import find_free_slots_tool,get_availability_tool,create_meeting_tool

def build_agent(creds: Credentials) -> Agent:
    return Agent(
        model=settings.bedrock_model_id,
        system_prompt=(
            "You are the orchestrator for a Slack-based meeting scheduling assistant. "
            "Users describe meetings they want to schedule in natural language. "
            "Use the tools available to find times, and respond concisely."
            "When a suitable slot is found and confirmed, book it immediately using create_meeting "
            "and include the Google Meet link in your response."
        ),
        tools=[find_free_slots_tool, get_availability_tool(creds),create_meeting_tool(creds)],
    )