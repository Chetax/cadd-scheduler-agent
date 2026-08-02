"""
Abstract UserRepository — the contract for user persistence.

Any concrete implementation (DynamoDB Local, real DynamoDB, in-memory
for tests) must implement these methods. Product code depends only on
this interface, never on a concrete class.
"""
from abc import ABC, abstractmethod
from backend.core.user import User

class UserNotFoundError(Exception):
    """Raised when a lookup misses. Caller decides whether that's fatal."""
    pass


class UserAlreadyExistsError(Exception):
    """Raised on create() if a row with the same slack_user_id exists."""
    pass

class UserRepository(ABC):
    """
    Abstract phonebook for User records.

    Access patterns intentionally limited to what the app actually needs:
    lookup by Slack id (primary path), lookup by email (attendee resolution),
    create (onboarding), update onboarding state (post-consent).

    No `list_all`, no `delete` — YAGNI. Add later if a use case shows up.
    """

    @abstractmethod
    def get_by_slack_user_id(self, slack_user_id: str) -> User | None:
        """Return the user, or None if not found. Primary lookup path."""
        ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """
        Return the user by email, or None. Uses the email-index GSI.

        Used when an attendee is referenced by email rather than Slack handle,
        e.g. someone types `/cadd schedule with donald@company.com`.
        """
        ...

    @abstractmethod
    def create(self, user: User) -> User:
        """
        Persist a new user. Raises UserAlreadyExistsError if slack_user_id
        collides. Returns the user (unchanged, but consistent with a future
        world where the repo assigns server-side fields).
        """
        ...

    @abstractmethod
    def mark_authorized(self, slack_user_id: str) -> User:
        """
        Flip onboarding_state to AUTHORIZED and bump updated_at.
        Raises UserNotFoundError if the row doesn't exist.
        Returns the updated user.
        """
        ...