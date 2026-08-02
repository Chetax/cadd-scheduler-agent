"""Quick smoke test for DynamoDBUserRepository."""
import uuid
from backend.integrations.dynamodb.user_repository import DynamoDBUserRepository
from backend.core.user import User, OnboardingState

repo = DynamoDBUserRepository()

# Create
donald = User(
    slack_user_id="U_DONALD_TEST",
    email="donald@test.com",
    agentcore_user_id=uuid.uuid4().hex,
    slack_team_id="T_TEST",
)
repo.create(donald)
print("Created:", donald)

# Read by PK
print("By slack id:", repo.get_by_slack_user_id("U_DONALD_TEST"))

# Read by GSI
print("By email:", repo.get_by_email("donald@test.com"))

# Update
updated = repo.mark_authorized("U_DONALD_TEST")
print("After authorize:", updated.onboarding_state)

# Miss
print("Missing user:", repo.get_by_slack_user_id("U_NOPE"))