"""
Google Calendar implementation of CalendarProvider.

Takes a Credentials object in the constructor — doesn't know or care
where it came from (a local token file today, AgentCore Identity later).
"""
from datetime import datetime,timedelta,timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.integrations.calendar_provider import(
    CalendarProvider,
    BusySlot,
    MeetingDetails,
) 
from backend.core.logging import get_logger
logger = get_logger(__name__)

class GoogleCalendarProvider(CalendarProvider):
    def __init__(self,credentials:Credentials):
        self._creds = credentials
        self._service = build(
            "calendar", "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def get_availability(self, user_ids: list[str], start: datetime, end: datetime) -> dict[str, list[BusySlot]]:
        body = {
            "timeMin": start.astimezone(timezone.utc).isoformat(),
            "timeMax": end.astimezone(timezone.utc).isoformat(),
            "items": [{"id": email} for email in user_ids],
        }
        try:
            response = self._service.freebusy().query(body=body).execute()
        except HttpError as e:
            raise RuntimeError(f"freebusy query failed: {e}") from e

        result: dict[str, list[BusySlot]] = {}
        for email, cal_info in response.get("calendars", {}).items():
            errors = cal_info.get("errors", [])
            if errors:
                # token missing or no access — log it, don't silently return []
                logger.warning(f"freebusy error for {email}: {errors}")
            result[email] = [
                BusySlot(start=slot["start"], end=slot["end"])
                for slot in cal_info.get("busy", [])
            ]
        return result

    def create_meeting(
        self,
        organizer_id: str,
        attendee_ids: list[str],
        start: datetime,
        end: datetime,
         title: str,
    ) -> MeetingDetails:
        event_body = {
            "summary": title,
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
            "attendees": [{"email": email} for email in attendee_ids],
            "conferenceData": {
                "createRequest": {
                    "requestId": f"{organizer_id}-{start.timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        try:
            created = (
                self._service.events()
                .insert(
                    calendarId="primary",
                    body=event_body,
                    conferenceDataVersion=1,
                    sendUpdates="all",
                )
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"event creation failed: {e}") from e

        return MeetingDetails(
            event_id=created["id"],
            join_url=created.get("hangoutLink", ""),
            start=start,
            end=end,
        )
