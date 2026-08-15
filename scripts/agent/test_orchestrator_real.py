"""
Smoke test for the orchestrator agent with real Google Calendar data.

Feeds the agent a natural-language scheduling request. The agent should:
  1. Call get_availability_tool to check calendars
  2. Call find_free_slots_tool on the busy blocks
  3. Return proposed free windows

Usage:
    PYTHONPATH=. python scripts/agent/test_orchestrator_real.py <email1> [email2 ...]

Requires the following in .env:
    test_slack_user_id
    test_slack_team_id
"""

import asyncio
from zoneinfo import ZoneInfo
from datetime import datetime,timedelta
import sys
from backend.agents.orchestrator import build_agent
from backend.integrations.dynamodb.user_repository import DynamoDBUserRepository
from backend.integrations.dynamodb.pending_session_repository import DynamoDBPendingSessionRepository
from backend.integrations.tokens.agentcore_lookup import AgentCoreUserCredentialsLookup
from backend.integrations.slack.slack_user_info_provider import SlackWebClientUserInfoProvider
from backend.core.onboarding_service import OnboardingService, OnboardingRequired
from slack_sdk import WebClient
from backend.core.config import settings


onboarding_service = OnboardingService(
    user_repo=DynamoDBUserRepository(),
    pending_repo=DynamoDBPendingSessionRepository(),
    credentials_lookup=AgentCoreUserCredentialsLookup(),
    slack_user_info_provider=SlackWebClientUserInfoProvider(
        WebClient(token=settings.slack_bot_token)
    ),
)


if len(sys.argv) < 2:
    print("Usage: python scripts/agent/test_orchestrator_real.py <email1> [email2 ...]")
    sys.exit(1)

emails = sys.argv[1:]

async def main():
    creds = await onboarding_service.get_credentials_for_slack_user(
        slack_user_id=settings.test_slack_user_id,
        slack_team_id=settings.test_slack_team_id,
    )
    agent = build_agent(creds)
    ist = ZoneInfo("Asia/Kolkata")
    today = datetime.now(ist).date()
    days_ahead = (1 - today.weekday()) % 7 or 7
    next_tuesday = today + timedelta(days=days_ahead)

    message = (
        f"Find a 30-minute meeting window on {next_tuesday.isoformat()} "
        f"between 00:00 and 02:30 IST (+05:30) "
        f"for the following people: {', '.join(emails)}."
    )

    agent(message)

asyncio.run(main())