"""
DynamoDB-backed PendingSessionRepository.

Concrete implementation of the abstract PendingSessionRepository
contract, backed by the cadd_pending_sessions table.
"""

import boto3
from datetime import datetime, timezone

from backend.core.config import settings
from backend.core.pending_session import PendingSession
from backend.core.pending_session_repository import PendingSessionRepository

TABLE_NAME = "cadd_pending_sessions"

class DynamoDBPendingSessionRepository(PendingSessionRepository):
    def __init__(
        self,
        endpoint_url: str = settings.table_endpoint_url,
        region_name: str = settings.aws_region,
        aws_access_key_id: str = "fake",
        aws_secret_access_key: str = "fake",
    ) -> None:
        self._dynamodb = boto3.resource(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self._table = self._dynamodb.Table(TABLE_NAME)

    def _to_item(self, session: PendingSession) -> dict:
        """
        PendingSession -> DynamoDB item dict.

        Note: `expires_at` is stored as a Unix INT (seconds since epoch),
        not an ISO string. DynamoDB TTL only recognizes integer timestamps
        — storing an ISO string means TTL silently never fires and rows
        live forever. Classic footgun.
        """
        return {
            "session_id": session.session_id,
            "agentcore_user_id": session.agentcore_user_id,
            "slack_user_id": session.slack_user_id,
            "expires_at": int(session.expires_at.timestamp()),
            "created_at": session.created_at.isoformat(),
        }
    
    def _from_item(self, item: dict) -> PendingSession:
        """DynamoDB item dict -> PendingSession. Inverse of _to_item."""
        return PendingSession(
            session_id=item["session_id"],
            agentcore_user_id=item["agentcore_user_id"],
            slack_user_id=item["slack_user_id"],
            # `expires_at` is stored as a Decimal (Dynamo's number type),
            # convert to int then back to datetime.
            expires_at=datetime.fromtimestamp(
                int(item["expires_at"]), tz=timezone.utc
            ),
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def create(self, session: PendingSession) -> PendingSession:
        # No ConditionExpression: overwriting an existing pending session
        
        self._table.put_item(Item=self._to_item(session))
        return session

    def pop(self, session_id: str) -> PendingSession | None:
        """
        Atomic get-and-delete. `delete_item` with `ReturnValues="ALL_OLD"`
        returns the item as it existed BEFORE deletion, in a single call.
        Two callbacks racing on the same session_id: one wins and gets
        the row, the other gets None. No lock, no coordination code.

        The item comes back under `response["Attributes"]` (Dynamo's
        general pattern for "here's what was there"). Absent if the row
        didn't exist — which is a normal, expected outcome for pop.
        """
        response = self._table.delete_item(
            Key={"session_id": session_id},
            ReturnValues="ALL_OLD",
        )
        item = response.get("Attributes")
        return self._from_item(item) if item else None

