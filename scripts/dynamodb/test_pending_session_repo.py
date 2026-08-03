"""Quick smoke test for DynamoDBPendingSessionRepository."""
import uuid
from backend.core.pending_session import PendingSession
from backend.integrations.dynamodb.pending_session_repository import (
    DynamoDBPendingSessionRepository,
)

repo = DynamoDBPendingSessionRepository()

# Create
session = PendingSession(
    session_id=f"sess_{uuid.uuid4().hex[:8]}",
    agentcore_user_id="85a73e1c",
    slack_user_id="U0BLEHL62Q4",
)
repo.create(session)
print("Created:", session)

# Pop — should return the session we just created
popped = repo.pop(session.session_id)
print("Popped:", popped)

# Pop again — should be None (already deleted)
popped_again = repo.pop(session.session_id)
print("Pop again (expect None):", popped_again)

# Pop a session that never existed
never_existed = repo.pop("sess_does_not_exist")
print("Never existed (expect None):", never_existed)