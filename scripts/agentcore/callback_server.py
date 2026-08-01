# scripts/agentcore/callback_server.py
"""
Local OAuth session-binding callback server for AgentCore Identity USER_FEDERATION flow.

Run:   python scripts/agentcore/callback_server.py
"""
import json
from pathlib import Path

import boto3
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

# Read the user_id that get_google_token.py is polling under.
# The SDK writes this to .agentcore.json when it first creates the workload identity.
AGENTCORE_CONFIG = Path(__file__).parent.parent.parent / ".agentcore.json"
with open(AGENTCORE_CONFIG) as f:
    _cfg = json.load(f)
USER_ID = _cfg["user_id"]

# Data-plane client (note: "bedrock-agentcore", NOT "bedrock-agentcore-control")
agentcore = boto3.client("bedrock-agentcore", region_name="us-east-1")


@app.get("/oauth2/callback")
async def oauth2_callback(request: Request):
    session_uri = request.query_params.get("session_id")
    if not session_uri:
        return {"error": "missing session_id query param"}

    print(f"\n--- Session-binding callback received ---")
    print(f"session_uri: {session_uri}")
    print(f"user_id:     {USER_ID}")

    agentcore.complete_resource_token_auth(
        sessionUri=session_uri,
        userIdentifier={"userId": USER_ID},
    )

    print("--- complete_resource_token_auth OK — token should now be released ---\n")
    return {"status": "authorized, you can close this tab"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)