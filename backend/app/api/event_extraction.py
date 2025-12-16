import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from fastapi import FastAPI
from fastapi import APIRouter
from pydantic import BaseModel

class EventExtract(BaseModel):
    email:str 
    start_time:str
    end_time:str


SCOPES = ["https://www.googleapis.com/auth/calendar"]

router=APIRouter(
    prefix='/get_free_busy',
    tags=['get_free_busy']
)

def get_credentials():
    creds = None
    if os.path.exists("app/api/event_token.json"):
        creds = Credentials.from_authorized_user_file("app/api/event_token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "app/api/credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("app/api/event_token.json", "w") as token:
            token.write(creds.to_json())

    return creds


@router.get("")
def get_free_busy(payload:EventExtract):
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    body = {
        "timeMin": payload.start_time,
        "timeMax": payload.end_time,
        "items": [{"id": payload.email}],
    }

    response= service.freebusy().query(body=body).execute()
    busy_slots = response.get("calendars", {}).get(payload.email, {}).get("busy", [])
    if not busy_slots:
        print("No busy slots. Person is free in this window.")
        return{
            "success":"true",
            "message":"No busy slots. Person is free in this window.",
            "status":200
        }
    
    print("Busy slots:")
    busy_time=[]

    for slot in busy_slots:
        busy_time.append(f"{slot['start']} → {slot['end']}")
    
    return{
            "success":"true",
            "message":f"busy slots : {busy_time}",
            "status":200
        }



def main():

    email = "chetan@consultadd.com"
    
    start_time = "2025-12-17T00:00:00Z"
    end_time   = "2025-12-17T23:59:59Z"

    response = get_free_busy(email, start_time, end_time)
    print(response)


if __name__ == "__main__":
    main()
