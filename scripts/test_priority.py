"""
Priority test — proves the AgentCore-Identity-backed credential model works.

Fetches ACTING_EMAIL's credentials from AgentCore Identity vault →
creates a meeting inviting ATTENDEES → event lands on their calendars only;
Chetan's personal calendar is untouched.
"""

import argparse
import asyncio                                                    
from datetime import datetime, timedelta, timezone

from backend.integrations.google_calendar.provider import GoogleCalendarProvider
from backend.integrations.tokens.agentcore_lookup import (
    AgentCoreUserCredentialsLookup,
)

# Hardcoded for MVP — only one AgentCore user_id exists right now.
# When Slack integration lands, this'll be looked up per Slack user.
USER_ID = "85a73e1c"


parser = argparse.ArgumentParser()
parser.add_argument("--acting-email", required=True,
                    help="Google email of the acting user (must match the "
                         "account authorized in AgentCore Identity)")
parser.add_argument("--attendee", action="append", required=True,
                    help="attendee email (repeat flag for multiple)")
args = parser.parse_args()

ACTING_EMAIL = args.acting_email
ATTENDEES = args.attendee


async def main():
    # Fetch credentials from AgentCore vault
    lookup = AgentCoreUserCredentialsLookup()
    creds = await lookup.get_google_credentials(USER_ID)

    provider = GoogleCalendarProvider(creds)

    # 1) Free/busy check
    availability = provider.get_availability(
        user_ids=[ACTING_EMAIL] + ATTENDEES,
        date=datetime.now(timezone.utc),
    )
    print("--- Free/busy today ---")
    for email, busy in availability.items():
        print(f"  {email}: {len(busy)} busy slot(s)")
        for b in busy:
            print(f"     {b.start} → {b.end}")

    # 2) Create a meeting ~1 day out, 15 minutes long
    start = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).replace(microsecond=0)
    end = start + timedelta(minutes=15)

    meeting = provider.create_meeting(
        organizer_id=ACTING_EMAIL,
        attendee_ids=ATTENDEES,
        start=start,
        end=end,
        title="[TEST] cadd-scheduler AgentCore credential model verification",
    )

    print("\n--- Meeting created ---")
    print(f"  event_id : {meeting.event_id}")
    print(f"  meet link: {meeting.join_url}")
    print(f"  window   : {meeting.start} → {meeting.end}")
    print(
        "\nCheck:\n"
        f"  ✓ Event on {ACTING_EMAIL}'s calendar (as organizer)\n"
        f"  ✓ Event on each attendee's calendar (as invitee)\n"
        "  ✓ Meet link opens a real Meet room\n"
        "\nDelete the event afterward."
    )


if __name__ == "__main__":
    asyncio.run(main())