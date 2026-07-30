"""
One-time OAuth flow. Run once per test user.

Usage:
    python scripts/connect_user.py chetan
    python scripts/connect_user.py mohit
    python scripts/connect_user.py ashwin

Opens a browser, the user consents, refresh token saved to
backend/integrations/tokens/<name>_token.json.

IMPORTANT: the `name` argument is just a filename label. The token
belongs to whoever actually clicks "Allow" in the browser.
"""

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

CREDENTIALS_PATH = Path("backend/integrations/credentials.json")
TOKENS_DIR = Path("backend/integrations/tokens")


def connect_user(name: str) -> None:
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    token_path = TOKENS_DIR / f"{name}_token.json"

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    token_path.write_text(creds.to_json())
    print(f"✓ Saved token for '{name}' → {token_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/connect_user.py <name>")
        sys.exit(1)
    connect_user(sys.argv[1])