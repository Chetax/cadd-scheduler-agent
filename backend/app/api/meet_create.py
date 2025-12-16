from __future__ import print_function

import os.path
from fastapi import FastAPI
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.apps import meet_v2
from fastapi import APIRouter


router=APIRouter(
    prefix="/Gmeet",
    tags=['Gmeet']
)
# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/meetings.space.created']

@router.get('/createGmeet')
def createGmeet():
    """Shows basic usage of the Google Meet API.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('app/api/Gmeet_token.json'):
        creds = Credentials.from_authorized_user_file('app/api/Gmeet_token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'app/api/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('app/api/Gmeet_token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        client = meet_v2.SpacesServiceClient(credentials=creds)
        request = meet_v2.CreateSpaceRequest()
        response = client.create_space(request=request)
        print(f'Space created: {response.meeting_uri}')
        return {
            "status":"200",
            "message":"Gmeet meeting created sucessfully",
            "meeting_url":response.meeting_uri,
            }
    except Exception as error:
        print(f'An error occurred: {error}')
        return {
            "status":"500",
            "message":"Internal Server Error",
            "meeting_url":response.meeting_uri,
            }

