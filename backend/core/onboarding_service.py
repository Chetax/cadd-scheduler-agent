# backend/core/onboarding_service.py
"""
OnboardingService — the entry point every Slack handler calls to get
Google credentials for a Slack user.

Handles three branches:
  1. User exists and is authorized → return credentials.
  2. User exists but is pending    → refresh OAuth kickoff, re-raise OnboardingRequired.
  3. User doesn't exist            → resolve email, kick off OAuth, persist state,
                                     raise OnboardingRequired.

All dependencies are abstract — inject fakes for unit tests.
"""
import logging
import uuid

from google.oauth2.credentials import Credentials

from backend.core.user_credentials_lookup import (
    UserCredentialsLookup,
    UserNotAuthorizedError,
)
from backend.core.slack_user_info_provider import SlackUserInfoProvider
from backend.core.user_repository import UserRepository
from backend.core.pending_session_repository import PendingSessionRepository
from backend.core.user import User, OnboardingState  # adjust if your enum lives elsewhere
from backend.core.pending_session import PendingSession

logger = logging.getLogger(__name__)


class OnboardingRequired(Exception):
    """Raised when the caller must send the user to complete OAuth consent.

    Carries the auth_url to DM to the Slack user.
    """

    def __init__(self, auth_url: str):
        super().__init__(f"User must complete onboarding at {auth_url}")
        self.auth_url = auth_url


class OnboardingService:
    """Resolves Slack user IDs to Google credentials, orchestrating onboarding when needed."""

    def __init__(
        self,
        user_repo: UserRepository,
        pending_repo: PendingSessionRepository,
        credentials_lookup: UserCredentialsLookup,
        slack_user_info_provider: SlackUserInfoProvider,
    ):
        self._user_repo = user_repo
        self._pending_repo = pending_repo
        self._credentials_lookup = credentials_lookup
        self._slack_user_info = slack_user_info_provider

    async def get_credentials_for_slack_user(self, slack_user_id: str, slack_team_id: str) -> Credentials:
        user = self._user_repo.get_by_slack_user_id(slack_user_id)

        if user is None:
            return await self._onboard_new_user(slack_user_id, slack_team_id)

        # Branches 1 & 2: user exists. Ask the vault. If it hands back creds,
        # we're done. If it says "not authorized," treat it as re-onboarding.
        # TODO: if user.state == AUTHORIZED but vault raises, we don't currently
        #       flip state back to PENDING (UserRepository has no mark_pending).
        #       DB state may briefly lie during re-auth. Add mark_pending() later.
        try:
            return await self._credentials_lookup.get_google_credentials(
                user.agentcore_user_id
            )
        except UserNotAuthorizedError as e:
            self._pending_repo.create(
                PendingSession(
                    session_id=e.session_id,
                    agentcore_user_id=user.agentcore_user_id,
                    slack_user_id=slack_user_id,
                )
            )
            raise OnboardingRequired(auth_url=e.auth_url) from e

    async def _onboard_new_user(self, slack_user_id: str,slack_team_id: str) -> Credentials:
        """Resolve email, generate agentcore_user_id, kick off OAuth,
        persist PendingSession + User (PENDING), raise OnboardingRequired.

        Never returns credentials in practice — a brand-new user has no
        token in the vault, so the lookup always raises. The `return` at
        the bottom exists only for the theoretical case where the vault
        somehow already has a token for a freshly-minted agentcore_user_id
        (should never happen; logged loudly if it does).
        """
        email = self._slack_user_info.get_email(slack_user_id)
        agentcore_user_id = uuid.uuid4().hex[:8]  # match Session 2 format

        try:
            creds = await self._credentials_lookup.get_google_credentials(
                agentcore_user_id
            )
        except UserNotAuthorizedError as e:
            # Persist PendingSession first (self-healing via TTL if User write fails),
            # then User row.
            self._pending_repo.create(
                PendingSession(
                    session_id=e.session_id,
                    agentcore_user_id=agentcore_user_id,
                    slack_user_id=slack_user_id,
                )
            )
            self._user_repo.create(
                User(
                    slack_user_id=slack_user_id,
                    slack_team_id=slack_team_id,
                    agentcore_user_id=agentcore_user_id,
                    email=email,
                    onboarding_state=OnboardingState.PENDING,
                )
            )
            raise OnboardingRequired(auth_url=e.auth_url) from e

        # Unreachable in practice — a freshly-generated agentcore_user_id can't
        # already have a token. Log and persist as authorized just in case.
        logger.error(
            "unexpected: new user %s got credentials without onboarding", slack_user_id
        )
        self._user_repo.create(
            User(
                slack_user_id=slack_user_id,
                slack_team_id=slack_team_id,
                agentcore_user_id=agentcore_user_id,
                email=email,
                onboarding_state=OnboardingState.AUTHORIZED,
            )
        )
        return creds