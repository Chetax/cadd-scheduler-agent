# backend/core/user_credentials_lookup.py
"""
UserCredentialsLookup — the credentials phonebook.

Given a user_id, returns the OAuth credentials that user has granted us
for a specific service (currently Google Calendar).

This module deliberately says nothing about *where* those credentials
come from. Concrete implementations plug in the backend:

  - AgentCoreUserCredentialsLookup — production, backed by AgentCore Identity vault
  - MockUserCredentialsLookup       — unit tests, returns fake credentials
  - LocalFileUserCredentialsLookup  — offline dev, reads tokens/<user_id>.json

Callers should type-hint against UserCredentialsLookup, never against a
concrete class, so the backend can swap without touching caller code.
"""
from abc import ABC, abstractmethod

from google.oauth2.credentials import Credentials


class UserCredentialsLookup(ABC):
    """Abstract source of user OAuth credentials."""

    @abstractmethod
    async def get_google_credentials(self, user_id: str) -> Credentials:
        """Return Google OAuth credentials for the given user_id.

        Args:
            user_id: The internal user identifier (e.g. a Slack user ID
                     or an AgentCore user_id). Must have already
                     completed the OAuth consent flow.

        Returns:
            A Google Credentials object suitable for passing to
            GoogleCalendarProvider.

        Raises:
            UserNotAuthorizedError: user_id has never consented, or
                                    their consent was revoked.
            CredentialsExpiredError: credentials exist but can no longer
                                     be refreshed.
        """
        ...


class UserNotAuthorizedError(Exception):
    """Raised when a user has no valid credentials in the lookup.

    Carries the auth_url when known, so callers (e.g. a Slack bot)
    can send it to the user to complete onboarding.
    """

    def __init__(self, message: str, auth_url: str | None = None):
        super().__init__(message)
        self.auth_url = auth_url


class CredentialsExpiredError(Exception):
    """Raised when credentials exist but are no longer usable."""