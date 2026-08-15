from strands import Agent
from google.oauth2.credentials import Credentials
from backend.core.config import settings
from backend.agents.availability import find_free_slots_tool,get_availability_tool

def build_agent(creds: Credentials) -> Agent:
    return Agent(
        model=settings.bedrock_model_id,
        system_prompt=(
            "You are the orchestrator for a Slack-based meeting scheduling assistant. "
            "Users describe meetings they want to schedule in natural language. "
            "Use the tools available to find times, and respond concisely."
        ),
        tools=[find_free_slots_tool, get_availability_tool(creds)],
    )