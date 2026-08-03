"""
Abstract PendingSessionRepository — the contract for pending OAuth
session persistence.

A pending session is the short-lived row that bridges the two halves
of an OAuth flow: the backend that starts the flow (and knows which
user it belongs to) and the callback server that finishes the flow
(and only knows the session_id). This repository is how those two
processes share state.

Any concrete implementation (DynamoDB, in-memory fake for tests,
Redis in the future) must implement the two methods below.
"""

from abc import ABC, abstractmethod

from backend.core.pending_session import PendingSession


class PendingSessionRepository(ABC):
    @abstractmethod
    def create(self, session: PendingSession) -> PendingSession:
        """
        Persist a pending session. Overwrites silently on session_id
        collision — session_ids are AgentCore-generated and unique in
        practice, and re-writing an in-flight session with the same
        data is harmless.

        Returns the session as persisted.
        """
        ...

    @abstractmethod
    def pop(self, session_id: str) -> PendingSession | None:
        """
        Atomically read-and-delete a pending session.

        Returns the deleted session, or None if no row existed under
        that session_id. None is expected in two legitimate cases:
          - The session expired (TTL cleaned it up) before the callback.
          - A duplicate callback fired — the first pop succeeded, the
            second finds nothing.

        Implementations must guarantee atomicity so concurrent callbacks
        can't both process the same session. In DynamoDB, this is done
        via `delete_item` with `ReturnValues="ALL_OLD"`.
        """
        ...