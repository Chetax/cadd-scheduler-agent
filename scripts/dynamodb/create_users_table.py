"""
Create the cadd_users DynamoDB table.

This table stores the Slack↔email↔AgentCore-Identity mapping. Tokens
themselves live in AgentCore Identity's token vault (not here) — this
table only holds pointers to vault entries.

Access patterns:
  - Fetch by slack_user_id (primary key)
  - Fetch by email (GSI: email-index)
"""

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "cadd_users"


DYNAMODB_CONFIG = {
    "endpoint_url": "http://localhost:8000",
    "region_name": "us-east-1",
    "aws_access_key_id": "fake",
    "aws_secret_access_key": "fake",
}


def create_users_table() -> None:
    client = boto3.client("dynamodb", **DYNAMODB_CONFIG)

    # AttributeDefinitions: declare the TYPES of attributes used in keys
    attribute_definitions = [
        {"AttributeName": "slack_user_id", "AttributeType": "S"},   # S = String
        {"AttributeName": "email", "AttributeType": "S"},
    ]

    # KeySchema: the primary key. HASH = partition key.
    key_schema = [
        {"AttributeName": "slack_user_id", "KeyType": "HASH"},
    ]

    # GSI on email — lets us query "who owns this email?" without a table scan.
    # ProjectionType=ALL means the GSI stores a full copy of each item
    global_secondary_indexes = [
        {
            "IndexName": "email-index",
            "KeySchema": [
                {"AttributeName": "email", "KeyType": "HASH"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        },
    ]

    try:
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=attribute_definitions,
            KeySchema=key_schema,
            GlobalSecondaryIndexes=global_secondary_indexes,
            BillingMode="PAY_PER_REQUEST",   # PAY_PER_REQUEST = billing mode where you pay per read/write.
        )
        print(f"✓ Table '{TABLE_NAME}' created.")

        # Wait until the table is actually ready before returning.
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print(f"✓ Table '{TABLE_NAME}' is ACTIVE.")

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"• Table '{TABLE_NAME}' already exists. Nothing to do.")
        else:
            raise


if __name__ == "__main__":
    create_users_table()