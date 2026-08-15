"""
Smoke test for get_availability_tool.

Calls the tool directly (bypassing the LLM) against real Google Calendar data
via AgentCore-sourced credentials. Proves the tool's factory, closure, unwrap,
and rewrap logic all work end-to-end.

Usage:
    PYTHONPATH=. python scripts/agent/test_availability_tool_real.py <email1> [email2 ...]

Requires the following in .env:
    test_slack_user_id  — the Slack user whose credentials will be used
    test_slack_team_id  — the corresponding team ID
"""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys

from backend.agents.availability import get_availability_tool
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
    print("Usage: python scripts/test_availability_tool_real.py <email1> [email2 ...]")
    sys.exit(1)

emails = sys.argv[1:]

async def main():
    # 1. Get real credentials the same way webhooks.py does today.
    creds = await onboarding_service.get_credentials_for_slack_user(
        slack_user_id=settings.test_slack_user_id,
        slack_team_id=settings.test_slack_team_id
    )

    # 2. Build the tool.
    tool_fn = get_availability_tool(creds)

    # 3. Call it directly (not via LLM — direct Python invocation).
    ist = ZoneInfo("Asia/Kolkata")
    start = datetime.now(ist).replace(hour=17, minute=30, second=0, microsecond=0)
    end = start + timedelta(hours=9)

    result = tool_fn(
        emails=emails,
        start=start.isoformat(),
        end=end.isoformat(),
    )
    print(result)


asyncio.run(main())