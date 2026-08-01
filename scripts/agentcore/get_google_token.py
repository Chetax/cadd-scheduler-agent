"""
Fetch a Google OAuth token from AgentCore Identity's vault.

First run:
    - Prints an authorization URL. You visit it, log in with the Google
      account you want to connect (e.g. example@org.com), grant
      calendar access.
    - AgentCore captures the token via its callback URL, stores it in
      the vault, keyed by (workload identity, user_id).
    - Function returns the fresh access token.

Subsequent runs (same user_id):
    - No URL, no browser. Returns cached token from vault (or refreshes
      silently if expired). Fast.

Run:
    PYTHONPATH=. python scripts/agentcore/get_google_token.py
"""

import asyncio
import os 
from bedrock_agentcore.identity.auth import requires_access_token
PROVIDER_NAME = "google-calendar-oauth"

# Google scope for calendar access — same as GoogleCalendarProvider uses.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def _on_auth_url(url: str) -> None:
    """AgentCore calls this when it needs the user to authorize.
    We just print the URL for the user to open in a browser."""
    print("\n" + "=" * 70)
    print("👉 Open this URL in your browser to authorize:")
    print(url)
    print("=" * 70 + "\n")



@requires_access_token(
    provider_name=PROVIDER_NAME,
    scopes=SCOPES,
    # USER_FEDERATION = "a real human authorizes via a browser"
    # (vs. M2M which is for service-to-service, no human in the loop)
    auth_flow="USER_FEDERATION",
    on_auth_url=_on_auth_url,
    # force_authentication=False means "reuse cached token if valid"
    # Set to True to force a fresh consent flow every run (useful for
    # testing but noisy in normal use).
    force_authentication=False,
    callback_url=os.environ["CALLBACK_URL"]
    
)
async def fetch_token(access_token: str = "") -> str:
    """The decorator injects `access_token` before this function body runs."""
    
    return access_token

async def main() -> None:
    print("Requesting Google token from AgentCore Identity...")
    print(f"Provider: {PROVIDER_NAME}")
    print(f"Scopes:   {SCOPES}")

    token = await fetch_token()

    print("\n✓ Got a token!")
    # Only print prefix — access tokens are secrets.
    print(f"Token prefix: {token[:20]}...")
    print(f"Token length: {len(token)} chars")


if __name__ == "__main__":
    asyncio.run(main())