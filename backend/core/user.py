"""
User value object.

Represents one row in the cadd_users table. This is a plain data
container — no behavior, no persistence logic. Persistence lives in
UserRepository; this is just the shape of what flows in and out.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

class OnboardingState(str, Enum):
    """
    Where the user is in the Google OAuth flow.

    - PENDING: row created, auth_url DM'd, waiting on user to consent.
    - AUTHORIZED: token successfully bound in AgentCore vault. Ready to schedule.
    - REVOKED: user (or Google) invalidated the token; needs re-onboarding.

    Inheriting from `str` means the enum serializes cleanly to DynamoDB
    (which stores it as a plain string) and reads back as an OnboardingState.
    """
    PENDING = "pending"
    AUTHORIZED = "authorized"
    REVOKED = "revoked"    


@dataclass
class User:
    slack_user_id: str  
    email: str    
    agentcore_user_id: str   
    slack_team_id: str 
    timezone: str = "UTC"         
    onboarding_state: OnboardingState = OnboardingState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
