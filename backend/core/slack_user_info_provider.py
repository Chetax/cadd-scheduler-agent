"""
Abstract interface for looking up Slack user information.

Concrete impls live in `backend/integrations/slack/`.
Injected into `OnboardingService` so the service can be unit-tested with a fake.
"""
from abc import ABC, abstractmethod

class SlackUserInfoProvider(ABC):
    """Read-through interface to a Slack workspace's user directory."""

    @abstractmethod
    def get_email(self, slack_user_id: str) -> str:
        """Return the email address for the given Slack user ID.

        Raises:
            SlackUserInfoError: if the user is not found, has no email on
                their profile, or the underlying Slack call fails.
        """
        ...


class SlackUserInfoError(Exception):
    """Raised when a Slack user's email cannot be resolved."""