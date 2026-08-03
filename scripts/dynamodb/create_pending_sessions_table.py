"""
Create the cadd_pending_sessions DynamoDB table.

Ephemeral store mapping AgentCore OAuth session IDs to the user who
initiated the flow. Used by the callback server to figure out whose
token just landed in the vault, and to DM the right Slack user on
completion.

Rows auto-expire via DynamoDB TTL on the `expires_at` attribute
(unix timestamp), typically 30 minutes after creation. Abandoned
onboarding flows self-clean.

Access pattern:
  - Fetch by session_id (primary key), pop-and-delete on callback
"""

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "cadd_pending_sessions"


DYNAMODB_CONFIG = {
    "endpoint_url": "http://localhost:8000",
    "region_name": "us-east-1",
    "aws_access_key_id": "fake",
    "aws_secret_access_key": "fake",
}


def create_pending_sessions_table() -> None:
    client = boto3.client("dynamodb", **DYNAMODB_CONFIG)

    # AttributeDefinitions: declare the TYPES of attributes used in keys
    attribute_definitions = [
        {"AttributeName": "session_id", "AttributeType": "S"},
    ]

    # KeySchema: the primary key. HASH = partition key.
    key_schema = [
        {"AttributeName": "session_id", "KeyType": "HASH"},
    ]

    try:
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=attribute_definitions,
            KeySchema=key_schema,
            BillingMode="PAY_PER_REQUEST",
        )
        print(f"✓ Table '{TABLE_NAME}' created.")

        # Wait until the table is actually ready before returning.
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print(f"✓ Table '{TABLE_NAME}' is ACTIVE.")

        # Enable TTL on `expires_at`. Real Dynamo enforces this by scanning
        # for expired rows and deleting them within ~48h of expiration.
        # DynamoDB Local accepts the config but does not actually delete
        # expired items — fine for dev.

        client.update_time_to_live(
            TableName=TABLE_NAME,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "expires_at",
            },
        )
        print(f"✓ TTL enabled on 'expires_at'.")

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"• Table '{TABLE_NAME}' already exists. Nothing to do.")
        else:
            raise


if __name__ == "__main__":
    create_pending_sessions_table()