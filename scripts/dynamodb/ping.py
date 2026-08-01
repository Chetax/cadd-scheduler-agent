"""
Sanity check: can Python talk to DynamoDB Local?
"""
import boto3
client=boto3.client(
    "dynamodb",
    endpoint_url="http://localhost:8000",
    region_name="us-east-1",
    aws_access_key_id="fake",
    aws_secret_access_key="fake",
)
response = client.list_tables()
print("Connected. Tables:", response["TableNames"])