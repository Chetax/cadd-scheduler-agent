# scripts/test_onboarding.py
"""
End-to-end smoke test for OnboardingService.

Runs the full onboarding flow with real infrastructure:
  - DynamoDB Local (user + pending session tables)
  - AgentCore Identity (OAuth vault)
  - Slack Web API (users.info + chat.postMessage)

Prereqs (see progress log Session 4):
  - Callback server running on :8765 in another terminal
  - ngrok tunnel to :8765
  - CALLBACK_URL in .env matches current ngrok URL
  - AgentCore workload identity allowlist includes current ngrok URL
  - DynamoDB Local running on :8000

Run:
  PYTHONPATH=. python scripts/test_onboarding.py
  PYTHONPATH=. python scripts/test_onboarding.py --reset   # delete user row first
"""
import argparse
import asyncio
import logging
import sys

import boto3
from slack_sdk import WebClient

from backend.core.config import settings
from backend.core.onboarding_service import OnboardingService, OnboardingRequired
from backend.integrations.dynamodb.user_repository import DynamoDBUserRepository
from backend.integrations.dynamodb.pending_session_repository import (
    DynamoDBPendingSessionRepository,
)
from backend.integrations.tokens.agentcore_lookup import AgentCoreUserCredentialsLookup
from backend.integrations.slack.slack_user_info_provider import (
    SlackWebClientUserInfoProvider,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smoke")

SLACK_USER_ID = "U0BLEHL62Q4"
SLACK_TEAM_ID = "T0BL8T1QRPY"

def reset_user(slack_user_id: str) -> None:
    """Delete the user row so the smoke test exercises the new-user branch."""
    # Adjust endpoint_url + table name if your Session 3 setup differs.
    ddb = boto3.client("dynamodb", endpoint_url="http://localhost:8000", region_name="us-east-1")
    try:
        ddb.delete_item(
            TableName="cadd_users",
            Key={"slack_user_id": {"S": slack_user_id}},
        )
        logger.info("deleted user row for %s", slack_user_id)
    except Exception:
        logger.exception("reset failed — continuing anyway")


def build_service() -> OnboardingService:
    return OnboardingService(
        user_repo=DynamoDBUserRepository(),
        pending_repo=DynamoDBPendingSessionRepository(),
        credentials_lookup=AgentCoreUserCredentialsLookup(),
        slack_user_info_provider=SlackWebClientUserInfoProvider(
            WebClient(token=settings.slack_bot_token)
        ),
    )


async def main(reset: bool) -> int:
    if reset:
        reset_user(SLACK_USER_ID)

    service = build_service()

    print("\n" + "=" * 60)
    print(f"PHASE A — asking for credentials for {SLACK_USER_ID}")
    print("=" * 60)

    try:
        creds = await service.get_credentials_for_slack_user(SLACK_USER_ID,SLACK_TEAM_ID)
    except OnboardingRequired as e:
        print("\n→ OnboardingRequired raised (expected for new / pending user)")
        print(f"\n  Open this URL in a browser and click Allow:\n\n  {e.auth_url}\n")
        print("  Watch the callback server terminal — it should log the callback,")
        print("  mark_authorized, and slack DM. You should also get a DM in Slack.\n")
        input("  Press Enter here AFTER you've completed OAuth in the browser... ")
    else:
        print(f"\n→ Already authorized. token prefix: {creds.token[:20]}...")
        print("  (Skipping Phase B; run with --reset to exercise the new-user branch.)")
        return 0

    print("\n" + "=" * 60)
    print("PHASE C — asking again, expecting credentials this time")
    print("=" * 60)

    try:
        creds = await service.get_credentials_for_slack_user(SLACK_USER_ID, SLACK_TEAM_ID)
    except OnboardingRequired as e:
        print(f"\n✗ Still got OnboardingRequired: {e.auth_url}")
        print("  Something in the callback path didn't complete. Check:")
        print("   - callback server logs (did complete_resource_token_auth succeed?)")
        print("   - user_repo.mark_authorized log line (did the DB flip?)")
        print("   - DynamoDB user row (is onboarding_state = AUTHORIZED?)")
        return 1

    print(f"\n✓ Got credentials. token prefix: {creds.token[:20]}...")
    print("\nOnboarding flow works end-to-end. Ready for Slack app scaffolding.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete user row first to force new-user branch")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(reset=args.reset)))