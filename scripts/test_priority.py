"""
Priority test — proves the per-user-token model works.

Load ACTING_USER's token → create meeting inviting ATTENDEES →
event lands on their calendars only; Chetan's personal is untouched.
"""

from datetime import datetime, timedelta,timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from backend.integrations.google_calendar.provider import GoogleCalendarProvider

SCOPES = ["https://www.googleapis.com/auth/calendar"]

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--acting-user", required=True, help="token filename, e.g. 'chetan'")
parser.add_argument("--acting-email", required=True)
parser.add_argument("--attendee", action="append", required=True,
                    help="attendee email (repeat flag for multiple)")
args = parser.parse_args()

# --- Configure the test here ---
ACTING_USER = args.acting_user
ACTING_EMAIL = args.acting_email
ATTENDEES = args.attendee           
# ------------------------------


def load_creds(name: str) -> Credentials:
    path = Path(f"backend/integrations/tokens/{name}_token.json")
    if not path.exists():
        raise FileNotFoundError(
            f"No token for {name}. Run: python scripts/connect_user.py {name}"
        )
    return Credentials.from_authorized_user_file(str(path), SCOPES)


def main():
    creds = load_creds(ACTING_USER)
    provider = GoogleCalendarProvider(creds)

    # 1) Free/busy
    availability = provider.get_availability(
        user_ids=[ACTING_EMAIL] + ATTENDEES,
        date=datetime.now(timezone.utc),
    )
    print("--- Free/busy today ---")
    for email, busy in availability.items():
        print(f"  {email}: {len(busy)} busy slot(s)")
        for b in busy:
            print(f"     {b.start} → {b.end}")


    # 2) Create meeting ~1 day out, 15 minutes long
    start = (datetime.now(timezone.utc) + timedelta(days=1, hours=2)).replace(microsecond=0)
    end = start + timedelta(minutes=15)

    meeting = provider.create_meeting(
        organizer_id=ACTING_EMAIL,
        attendee_ids=ATTENDEES,
        start=start,
        end=end,
        title="[TEST] cadd-scheduler token model verification",
    )

    print("\n--- Meeting created ---")
    print(f"  event_id : {meeting.event_id}")
    print(f"  meet link: {meeting.join_url}")
    print(f"  window   : {meeting.start} → {meeting.end}")
    print(
        "\nCheck:\n"
        f"  ✓ Event on {ACTING_USER}'s calendar (as organizer)\n"
        f"  ✓ Event on each attendee's calendar (as invitee)\n"
        "  ✓ Meet link opens a real Meet room\n"
        "\nDelete the event afterward."
    )


if __name__ == "__main__":
    main()