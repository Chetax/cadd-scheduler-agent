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

    def _get_user_profile(self, slack_user_id: str) -> dict:
        if slack_user_id not in self._profile_cache:
            try:                                          # ← try/catch lives here
                response = self._client.users_info(user=slack_user_id)
            except SlackApiError as e:
                raise SlackUserInfoError(
                    f"Slack API call failed for user {slack_user_id}: {e.response['error']}"
                ) from e
            self._profile_cache[slack_user_id] = response.get("user", {}).get("profile", {})
        return self._profile_cache[slack_user_id]

    def get_email(self, slack_user_id: str) -> str:
    
        email = self._get_user_profile(slack_user_id).get("email")
        if not email:
            raise SlackUserInfoError(
                f"No email on profile for Slack user {slack_user_id} "
                f"(check users:read.email scope)"
            )
        return email

    def get_display_name(self, slack_user_id: str) -> str:

        profile = self._get_user_profile(slack_user_id)
        return profile.get("display_name") or profile.get("real_name") or slack_user_id