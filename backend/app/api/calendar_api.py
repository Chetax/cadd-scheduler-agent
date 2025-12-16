import datetime
import os.path
from fastapi import FastAPI
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List 

class DateTimeBlock(BaseModel):
    dateTime: str
    timeZone: str

class Attendee(BaseModel):
    email: str

class ReminderOverride(BaseModel):
    method: str
    minutes: int

class Reminders(BaseModel):
    useDefault: bool
    overrides: List[ReminderOverride]


class EventRequest(BaseModel):
    summary: str
    location: str
    description: str
    start: DateTimeBlock
    end: DateTimeBlock
    attendees: List[Attendee]
    reminders: Reminders


app=FastAPI()
router=APIRouter(
    prefix="/calendar",
    tags=["Calendar"]
)
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]




def get_credentials():
    creds = None

    if os.path.exists("app/api/token.json"):
        creds = Credentials.from_authorized_user_file("app/api/token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "app/api/credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("app/api/token.json", "w") as token:
            token.write(creds.to_json())

    return creds

@router.post('create_event_and_add_people')
def create_event_and_add_people(event:EventRequest):
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)
    event = service.events().insert(
        calendarId="primary",
        body=event,
        sendUpdates="all",
    ).execute()
    print("Event created:", event.get("htmlLink"))
    return {
        "status":"Event Created successfuly",
        "status-code":"200",
        "data":event.get("htmlLink")
    }




