"""
DynamoDB-backed UserRepository.

Concrete implementation of the abstract UserRepository contract, backed
by the cadd_users table (DynamoDB Local in dev, real DynamoDB in prod).
"""

import boto3
from botocore.exceptions import ClientError
from backend.core.user import User, OnboardingState
from backend.core.user_repository import (
    UserNotFoundError,
    UserAlreadyExistsError,
    UserRepository
)
from datetime import datetime, timezone
from backend.core.config import settings


class DynamoDBUserRepository(UserRepository):
    def __init__(
        self,
        endpoint_url: str = settings.table_endpoint_url,
        region_name: str = settings.aws_region,
        aws_access_key_id: str = "fake",
        aws_secret_access_key: str = "fake",
    )->None:
        self._dynamodb=boto3.resource(
            "dynamodb",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self._table = self._dynamodb.Table(settings.table_name)

    def _to_item(self, user: User) -> dict:
        """User -> DynamoDB item dict. Enums and datetimes need conversion."""
        return {
            "slack_user_id": user.slack_user_id,
            "email": user.email,
            "agentcore_user_id": user.agentcore_user_id,
            "slack_team_id": user.slack_team_id,
            "timezone": user.timezone,
            "onboarding_state": user.onboarding_state.value,   # enum -> str
            "created_at": user.created_at.isoformat(),         # datetime -> ISO str
            "updated_at": user.updated_at.isoformat(),
        }
    
    def _from_item(self, item: dict) -> User:
        """DynamoDB item dict -> User. Inverse of _to_item."""
        return User(
            slack_user_id=item["slack_user_id"],
            email=item["email"],
            agentcore_user_id=item["agentcore_user_id"],
            slack_team_id=item["slack_team_id"],
            timezone=item["timezone"],
            onboarding_state=OnboardingState(item["onboarding_state"]),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
        )

    def get_by_slack_user_id(self, slack_user_id: str) -> User | None:
        # get_item is a point lookup on the primary key. Cheapest read in Dynamo.
        response = self._table.get_item(Key={"slack_user_id": slack_user_id})
        # Miss returns a response WITHOUT the "Item" key. Not an error, just absent.
        item = response.get("Item")
        return self._from_item(item) if item else None

    def get_by_email(self, email: str) -> User | None:
        # GSI lookups use query(), not get_item(). GSIs aren't guaranteed unique,
        # so the API always returns a list. We take the first (and expect only one
        # since we control writes and email is de-facto unique per Workspace).
        from boto3.dynamodb.conditions import Key
        response = self._table.query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email),
        )
        items = response.get("Items", [])
        return self._from_item(items[0]) if items else None

    def create(self, user: User) -> User:
        try:
            # ConditionExpression is Dynamo's way of doing "insert only if not exists."
            # attribute_not_exists(slack_user_id) => this PK must not already be in the table.
            # Without this, put_item is an UPSERT and silently overwrites. Not what we want.
            self._table.put_item(
                Item=self._to_item(user),
                ConditionExpression="attribute_not_exists(slack_user_id)",
            )
            return user
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise UserAlreadyExistsError(
                    f"User {user.slack_user_id} already exists"
                ) from e
            raise  # anything else is a real error, don't swallow

    def mark_authorized(self, slack_user_id: str) -> User:
        now = datetime.now(timezone.utc)
        try:
            response = self._table.update_item(
                Key={"slack_user_id": slack_user_id},
                # UpdateExpression: which fields to change.
                # "SET foo = :val" is the syntax; :val is a placeholder bound below.
                UpdateExpression="SET onboarding_state = :state, updated_at = :updated",
                # ExpressionAttributeValues: bind the placeholders to real values.
                # Prefixed with `:` to distinguish from attribute NAMES (prefixed `#`).
                ExpressionAttributeValues={
                    ":state": OnboardingState.AUTHORIZED.value,
                    ":updated": now.isoformat(),
                },
                # Row must already exist — same conditional trick, inverted.
                ConditionExpression="attribute_exists(slack_user_id)",
                # Return the item AFTER the update so we can hydrate a User.
                ReturnValues="ALL_NEW",
            )
            return self._from_item(response["Attributes"])
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise UserNotFoundError(
                    f"User {slack_user_id} not found"
                ) from e
            raise
