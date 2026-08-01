"""
Smoke test — proves AgentCoreUserCredentialsLookup works end-to-end.

Fetches Chetan's Google credentials from AgentCore's vault and prints
whether we got a real token back.

Usage:
    PYTHONPATH=. python scripts/test_lookup.py
"""
import asyncio

from backend.integrations.tokens.agentcore_lookup import (
    AgentCoreUserCredentialsLookup,
)


# The AgentCore-side user_id that's already been onboarded.
# In .agentcore.json currently — for Chetan.
USER_ID = "85a73e1c"


async def main():
    lookup = AgentCoreUserCredentialsLookup()
    creds = await lookup.get_google_credentials(user_id=USER_ID)

    print("✓ Got credentials!")
    print(f"  token type:  {type(creds).__name__}")
    print(f"  token prefix: {creds.token[:20]}...")
    print(f"  token length: {len(creds.token)} chars")


if __name__ == "__main__":
    asyncio.run(main())