"""
AgentCoreUserCredentialsLookup — concrete UserCredentialsLookup backed by AgentCore Identity.

Multi-user by design. Each call fetches the token for a specific user_id
from AgentCore's KMS-encrypted vault. If that user hasn't onboarded,
raises UserNotAuthorizedError so the Slack layer can trigger onboarding.

Flow:
    1. Get a workload-access-token for this specific user_id.
       (Proves to AgentCore: "I'm asking on behalf of this user.")
    2. Use it to fetch the resource OAuth2 token (the Google token) from the vault.
    3. Wrap in google.oauth2.credentials.Credentials.
"""
import json
from pathlib import Path
import os
import boto3
from botocore.exceptions import ClientError
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
load_dotenv(".env")
from backend.core.user_credentials_lookup import (
    UserCredentialsLookup,
    UserNotAuthorizedError,
)



PROVIDER_NAME = "google-calendar-oauth"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class AgentCoreUserCredentialsLookup(UserCredentialsLookup):


    def __init__(self, region: str = "us-east-1", workload_identity_name: str | None = None):
        self._client = boto3.client("bedrock-agentcore", region_name=region)

        # Workload identity name: prefer explicit, else read from .agentcore.json
        if workload_identity_name is None:
            config_path = Path(__file__).parent.parent.parent.parent / ".agentcore.json"
            with open(config_path) as f:
                workload_identity_name = json.load(f)["workload_identity_name"]
        self._workload_identity_name = workload_identity_name

    async def get_google_credentials(self, user_id: str) -> Credentials:
        try:
            # Step 1: prove we're acting on behalf of this user
            wat_response = self._client.get_workload_access_token_for_user_id(
                workloadName=self._workload_identity_name,
                userId=user_id,
            )
            workload_access_token = wat_response["workloadAccessToken"]

            # Step 2: use it to fetch the Google token from the vault
            token_response = self._client.get_resource_oauth2_token(
                workloadIdentityToken=workload_access_token,
                resourceCredentialProviderName=PROVIDER_NAME,
                scopes=SCOPES,
                oauth2Flow="USER_FEDERATION",
                resourceOauth2ReturnUrl=os.getenv("CALLBACK_URL"),
            )
    
            access_token = token_response.get("accessToken")
            if not access_token:
                # No token in the response usually means "user must authorize" —
                # response would contain an authorizationUrl instead
                raise UserNotAuthorizedError(
                    f"user_id={user_id} needs to complete OAuth consent first"
                )

            return Credentials(token=access_token)

        except ClientError as e:
            raise UserNotAuthorizedError(
                f"Could not fetch credentials for user_id={user_id}: {e}"
            ) from e