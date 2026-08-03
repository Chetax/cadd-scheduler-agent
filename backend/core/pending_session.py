"""
PendingSession — ephemeral row tracking an in-flight OAuth onboarding.

Written when a user first triggers `/cadd` as the acting organizer and
needs to authorize Google Calendar. The row records "session_id X
belongs to agentcore_user_id Y (whose Slack id is Z)" so that when
AgentCore later fires the callback with only session_id in hand, we
can look up who owns the flow, bind the token to the right user, and
DM the right Slack user "✅ connected."

Rows are popped (get-and-delete) by the callback on success. Abandoned
sessions expire automatically via DynamoDB TTL on `expires_at`.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta


TTL_MINUTES = 30


@dataclass
class PendingSession:
    session_id: str
    agentcore_user_id: str
    slack_user_id: str
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTES)
    )
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )