"""
backend/agents/availability.py

Strands tool wrappers for calendar availability and booking.

Adapters only — the real logic lives in core/ and integrations/. Each tool
unwraps primitives at entry and rewraps at exit, because tool signatures must
be JSON-expressible for the LLM to call them.

Tools needing per-user credentials are factories: the outer function closes
over the provider, @tool goes on the inner function so creds stay invisible
to the model.

"""
from strands import tool
from datetime import datetime
from backend.core.availability import find_free_slots
from backend.integrations.calendar_provider import BusySlot
from typing import Callable
from backend.integrations.google_calendar.provider import GoogleCalendarProvider
from google.oauth2.credentials import Credentials

@tool
def find_free_slots_tool(
    busy_by_person: dict[str, list[dict]],
    search_start: str,
    search_end: str,
    duration_minutes: int,
) -> list[dict]:
    """
    Find windows of free time that work for a group of people.

    Use this when you need to find open meeting slots given each person's busy calendar blocks.

    Args:
        busy_by_person: Map of person identifier (email) to their busy blocks. Each block is a dict {"start": "<ISO 8601>", "end": "<ISO 8601>"}.
        search_start: Earliest possible meeting start, ISO 8601 with timezone offset.
        search_end: Latest possible meeting end, ISO 8601 with timezone offset.
        duration_minutes: Required meeting length in minutes.

    Returns:
        List of candidate free windows. Each window is guaranteed to be at least duration_minutes long, so a meeting of that length can be scheduled anywhere inside it. The window is not the meeting itself — pick a start time within the window as the actual proposed meeting time.    """

    unwrapped:dict[str, list[BusySlot]] = {}
    for email, blocks in busy_by_person.items():
        unwrapped[email] = [
            BusySlot(
                start=datetime.fromisoformat(b["start"]),
                end=datetime.fromisoformat(b["end"]),
            )
            for b in blocks
        ]
    start_dt = datetime.fromisoformat(search_start)
    end_dt = datetime.fromisoformat(search_end)

    free_slots = find_free_slots(unwrapped, start_dt, end_dt, duration_minutes)
    return [
        {"start": start.isoformat(), "end": end.isoformat()}
        for start, end in free_slots
    ]

def get_availability_tool(creds: Credentials) -> Callable:

    provider = GoogleCalendarProvider(creds)

    @tool
    def get_availability(
        emails: list[str],
        start: str,
        end: str,
    ) -> dict[str, list[dict]]:
        """Query the Google Calendar free/busy schedule for a set of people.

        Use this when you need to know when specific people are busy before proposing meeting times.
        Returns each person's busy blocks in the given time window.

        Args:
            emails: List of Google Workspace email addresses to query.
            start: Start of the time window to check, ISO 8601 with timezone offset.
            end: End of the time window to check, ISO 8601 with timezone offset.

        Returns:
            Map of email to list of busy blocks. Each busy block is a dict {"start": "<ISO 8601>", "end": "<ISO 8601>"}.
        """

        start_dt=datetime.fromisoformat(start)
        end_dt=datetime.fromisoformat(end)
        busy_by_person=provider.get_availability(emails, start_dt, end_dt)
        return {
            email: [
                {"start": slot.start.isoformat(), "end": slot.end.isoformat()}
                for slot in slots
            ]
            for email, slots in busy_by_person.items()
        }
    
    return get_availability

def create_meeting_tool(creds:Credentials)->Callable:
    provider = GoogleCalendarProvider(creds)

    @tool
    def create_meeting(
            organizer_id: str,
            attendee_ids: list[str],
            start: str,
            end: str,
            title: str,
        ) -> dict[str, str]:

            """Book a Google Meet for a group of people at a specific time.
            
                    Use this only after you have confirmed the slot is free for all attendees
                    using get_availability. Do not call this speculatively — it creates a real
                    calendar event and sends invites immediately.
            
                    Args:
                        organizer_id: Email of the person who ran the /cadd command.
                                        The event is created on their calendar.
                        attendee_ids: List of Google Workspace email addresses to invite.
                                        Do not include the organizer — Google adds them automatically.
                        start: Meeting start time, ISO 8601 with timezone offset.
                            Must be the exact start of the meeting, not the free window.
                        end: Meeting end time, ISO 8601 with timezone offset.
                        title: Short human-readable title for the calendar event.
            
                    Returns:
                        On success: {"join_url": "<Google Meet URL>", "event_id": "<calendar event id>"}
                        On failure: {"error": "<reason>"}
                        Always check for the "error" key before using the result.
            """
            
            start_dt=datetime.fromisoformat(start)
            end_dt=datetime.fromisoformat(end)

            try:
                meeting = provider.create_meeting(
                        organizer_id=organizer_id,
                        attendee_ids=attendee_ids,
                        start=start_dt,
                        end=end_dt,
                        title=title,
                    )
            except Exception as e:
                        return  {"error": f"event creation failed: {e}"}

            return {"join_url": meeting.join_url, "event_id":meeting.event_id}

    return create_meeting
        
        
                 
            
    

