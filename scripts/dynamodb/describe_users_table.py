"""
Inspect the cadd_users table's schema. Sanity check that create worked.

Run:
    PYTHONPATH=. python scripts/dynamodb/describe_users_table.py
"""

import json
import boto3

DYNAMODB_CONFIG = {
    "endpoint_url": "http://localhost:8000",
    "region_name": "us-east-1",
    "aws_access_key_id": "fake",
    "aws_secret_access_key": "fake",
}


def describe_table(table_name: str = "cadd_users") -> None:
    client = boto3.client("dynamodb", **DYNAMODB_CONFIG)
    response = client.describe_table(TableName=table_name)
    table = response["Table"]

    print(f"Table:  {table['TableName']}")
    print(f"Status: {table['TableStatus']}")
    print(f"Items:  {table.get('ItemCount', 0)}")

    print("\nKey schema:")
    for key in table["KeySchema"]:
        print(f"  {key['AttributeName']}  ({key['KeyType']})")

    print("\nAttribute definitions:")
    for attr in table["AttributeDefinitions"]:
        print(f"  {attr['AttributeName']}: {attr['AttributeType']}")

    if "GlobalSecondaryIndexes" in table:
        print("\nGlobal secondary indexes:")
        for gsi in table["GlobalSecondaryIndexes"]:
            keys = ", ".join(
                f"{k['AttributeName']} ({k['KeyType']})" for k in gsi["KeySchema"]
            )
            print(f"  {gsi['IndexName']}: {keys}")


if __name__ == "__main__":
    describe_table()