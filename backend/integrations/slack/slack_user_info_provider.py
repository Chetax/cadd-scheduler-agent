# backend/integrations/slack/slack_user_info_provider.py
"""
Slack WebClient-backed implementation of SlackUserInfoProvider.

Uses `users.info` (requires `users:read` and `users:read.email` scopes).
"""
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from backend.core.slack_user_info_provider import (
    SlackUserInfoProvider,
    SlackUserInfoError,
)

class SlackWebClientUserInfoProvider(SlackUserInfoProvider):
    """Resolves Slack user emails via the Slack Web API `users.info` endpoint."""

    def __init__(self, client: WebClient):
        self._client = client

    def get_email(self, slack_user_id: str) -> str:
        try:
            response = self._client.users_info(user=slack_user_id)
        except SlackApiError as e:
            raise SlackUserInfoError(
                f"Slack API call failed for user {slack_user_id}: {e.response['error']}"
            ) from e

        email = response.get("user", {}).get("profile", {}).get("email")
        if not email:
            raise SlackUserInfoError(
                f"No email on profile for Slack user {slack_user_id} "
                f"(check that the bot has the users:read.email scope and the user has an email set)"
            )

        return email