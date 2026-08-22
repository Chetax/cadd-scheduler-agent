"""
backend/api/webhooks.py

Slack webhook handlers.

Two routes, both signature-verified: /slack/commands for /cadd, and
/slack/actions for Block Kit button clicks. Each returns within Slack's
3-second limit and hands real work to a background task.

process_cadd_command is the main pipeline: resolve user -> parse mentions ->
parse time -> check availability -> book or offer alternatives.
"""
from backend.integrations.dynamodb.user_repository import DynamoDBUserRepository
from backend.integrations.dynamodb.pending_session_repository import DynamoDBPendingSessionRepository
from backend.integrations.tokens.agentcore_lookup import AgentCoreUserCredentialsLookup
from backend.integrations.slack.slack_user_info_provider import SlackWebClientUserInfoProvider
from backend.core.onboarding_service import OnboardingService, OnboardingRequired
from slack_sdk import WebClient
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from backend.core.config import settings
from backend.integrations.slack.signature_verifier import SlackSignatureVerifier, StaleSlackRequestError, InvalidSlackSignatureError
from backend.integrations.google_calendar.provider import GoogleCalendarProvider
from datetime import datetime, timedelta, time
from backend.integrations.bedrock.time_parser import BedrockTimeParser, TimeParseError
from backend.core.org_profile import OrgProfile, Shift
import re
import json
from backend.core.availability import find_free_slots
from zoneinfo import ZoneInfo
from backend.core.logging import get_logger
from backend.agents.orchestrator import build_agent

logger = get_logger(__name__)
router = APIRouter()

onboarding_service = OnboardingService(
    user_repo=DynamoDBUserRepository(),
    pending_repo=DynamoDBPendingSessionRepository(),
    credentials_lookup=AgentCoreUserCredentialsLookup(),
    slack_user_info_provider=SlackWebClientUserInfoProvider(
        WebClient(token=settings.slack_bot_token)
    ),
)
slack_client = WebClient(token=settings.slack_bot_token)
user_info_provider = SlackWebClientUserInfoProvider(slack_client)
time_parser = BedrockTimeParser(settings.bedrock_model_id, settings.aws_region)
org_profile = OrgProfile(org_id="consultadd", timezone="Asia/Kolkata")
default_shift = Shift(name="late", work_start=time(17, 30), work_end=time(2, 30))


async def process_cadd_command(user_id: str, team_id: str, text: str) -> None:
    acting_email = user_info_provider.get_email(user_id)

    try:
        creds = await onboarding_service.get_credentials_for_slack_user(user_id, team_id)
    except OnboardingRequired as e:
        slack_client.chat_postMessage(
            channel=user_id,
            text=f"\n  Open this URL in a browser and click Allow:\n\n  {e.auth_url}\n",
            unfurl_links=False,
            unfurl_media=False,
        )
        return

    mention_ids = re.findall(r"<@([A-Z0-9]+)(?:\|[^>]+)?>", text)
    if not mention_ids:
        slack_client.chat_postMessage(
            channel=user_id,
            text="Tag who you want to meet with, e.g. `/cadd meet with @mohit tomorrow at 3pm`",
        )
        return

    attendee_emails: list[str] = []
    attendee_display: dict[str, str] = {}
    for mentioned_user_id in mention_ids:
        email = user_info_provider.get_email(mentioned_user_id)
        name = user_info_provider.get_display_name(mentioned_user_id)
        if email:
            attendee_emails.append(email)
            attendee_display[email] = f"<@{mentioned_user_id}>"

    if not attendee_emails:
        slack_client.chat_postMessage(
            channel=user_id,
            text="Couldn't resolve any attendees — make sure you @mention them.",
        )
        return

    provider = GoogleCalendarProvider(creds)

    ist = org_profile.tz()
    now = datetime.now(ist)

    try:
        parsed = time_parser.parse(text, now=now, timezone=org_profile.timezone)
    except TimeParseError:
        slack_client.chat_postMessage(
            channel=user_id,
            text="I couldn't understand that time — try something like 'tomorrow at 3pm'.",
        )
        return

    start = parsed.start
    end = parsed.start + timedelta(minutes=parsed.duration_minutes)

    logger.info(f"Querying slot: {start} → {end} for {[acting_email] + attendee_emails}")
    if settings.use_agent:
        agent = build_agent(creds)
        result = agent(
            f"Schedule a {parsed.duration_minutes}-minute meeting.\n"
            f"Organizer: {acting_email}\n"
            f"Attendees: {', '.join(attendee_emails)}\n"
            f"Requested time: {start.isoformat()} to {end.isoformat()}\n"
            f"Check availability and book if the slot is free. "
            f"If the slot is busy, find the next free window that starts "
            f"at or after {start.isoformat()} within working hours "
            f"(5:30 PM to 2:30 AM IST) and book that instead.")
        slack_client.chat_postMessage(
            channel=user_id,
            text=str(result),
        )
        return

    query_start, query_end = default_shift.working_window(start, ist)

    busy_by_person = provider.get_availability(
        user_ids=[acting_email] + attendee_emails,
        start=query_start,
        end=query_end,
    )

    logger.info(f"Busy results: {busy_by_person}")

    conflicts = {
        email: [s for s in slots if s.start < end and s.end > start]
        for email, slots in busy_by_person.items()
    }
    conflicts = {e: s for e, s in conflicts.items() if s}

    if conflicts:
       

        free_slots = find_free_slots(
            busy_by_person=busy_by_person,
            search_start=query_start,
            search_end=query_end,
            duration_minutes=parsed.duration_minutes,
        )

        busy_names = [attendee_display.get(e, e) for e in conflicts]
        who = (
            f"{busy_names[0]} is busy"
            if len(busy_names) == 1
            else f"{len(busy_names)} attendees are busy ({', '.join(busy_names)})"
        )

        if free_slots:
            # free_slots are already the exact gaps — show them as ranges directly.
            # e.g. (5:30 PM, 10:00 PM) becomes "05:30 PM – 10:00 PM IST (4h 30m)"
            def format_duration(gap_start: datetime, gap_end: datetime) -> str:
                total_minutes = int((gap_end - gap_start).total_seconds() / 60)
                hours, mins = divmod(total_minutes, 60)
                if hours and mins:
                    return f"{hours}h {mins}m"
                elif hours:
                    return f"{hours}h"
                else:
                    return f"{mins}m"

            buttons = []
            for ind,(slot_start, slot_end) in enumerate(free_slots[:5]):
                buttons.append({
                    "type":'button',
                    "text":{
                        "type": "plain_text",
                        "text": f"{slot_start.astimezone(ist).strftime('%I:%M %p')} ({format_duration(slot_start, slot_end)} free)"
                    },
                    'action_id':f"book_slot_{ind}",
                    'value':json.dumps({"acting_email":acting_email,
                                        'attendee_emails':attendee_emails,
                                        'start':slot_start.isoformat(), 
                                        'end':(slot_start + timedelta(minutes=parsed.duration_minutes)).isoformat(),
                                        'team_id':team_id,
                                        'user_id':user_id})

                })


            slack_client.chat_postMessage(
                channel=user_id,
                text=(
                    f"❌ {who} at {start.astimezone(ist).strftime('%I:%M %p IST')}\n\n"
                ),
                blocks=[{'type':'section','text':{'type': 'mrkdwn', 'text': f"❌ {who} at {start.astimezone(ist).strftime('%a %d %b, %I:%M %p IST')} — pick a free window:"}},{ 'type':'actions','elements':buttons}]
            )
        else:
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"❌ {who} at {start.astimezone(ist).strftime('%I:%M %p IST')}\n\nNo free slots in working hours.",
            )
        return

    # no conflicts — book it
    meeting = provider.create_meeting(
        organizer_id=acting_email,
        attendee_ids=attendee_emails,
        start=start,
        end=end,
        title="Meeting scheduled via cadd",
    )

    logger.info(f"Meeting created: {meeting.join_url}")
    slack_client.chat_postMessage(
        channel=user_id,
        text=(
        f"✅ No conflicts found!\n"
        f"🕒 Slot: {start.astimezone(ist).strftime('%I:%M %p')} – "
        f"{end.astimezone(ist).strftime('%I:%M %p')} IST\n"
        f"👥 Attendees: {', '.join(attendee_display.values())}\n"
        f"🔗 {meeting.join_url}\n"
    ),
    )


async def handle_book_slot(user_id:str, team_id:str, acting_email:str, attendee_emails:list[str], start, end):

    try:
        creds = await onboarding_service.get_credentials_for_slack_user(user_id, team_id)
    except OnboardingRequired as e:
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"\n  Open this URL in a browser and click Allow:\n\n  {e.auth_url}\n",
                unfurl_links=False,
                unfurl_media=False,
            )
            return
    
    provider = GoogleCalendarProvider(creds)
    meeting = provider.create_meeting(
            organizer_id=acting_email,
            attendee_ids=attendee_emails,
            start=start,
            end=end,
            title="Meeting scheduled via cadd",
        )

    ist = org_profile.tz()


    slack_client.chat_postMessage(
            channel=user_id,
            text=(
            f"🕒 Slot: {start.astimezone(ist).strftime('%I:%M %p')} – "
            f"{end.astimezone(ist).strftime('%I:%M %p')} IST\n"
            f"👥 Attendees: {', '.join(attendee_emails)}\n"
            f"🔗 {meeting.join_url}\n"
        ),)




    

@router.post("/slack/commands")
async def slack_webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if timestamp is None or signature is None:
        raise HTTPException(status_code=401, detail="Missing Slack signature headers")

    slack_instance = SlackSignatureVerifier(settings.slack_signing_secret)

    try:
        slack_instance.verify(timestamp, signature, raw_body)
    except StaleSlackRequestError as e:
        raise HTTPException(status_code=401, detail=f"Stale Slack Request Error : {e}")
    except InvalidSlackSignatureError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Slack Signature Error : {e}")

    formObj = await request.form()
    user_id = formObj.get("user_id")
    team_id = formObj.get("team_id")
    text = formObj.get("text")

    background_tasks.add_task(process_cadd_command, user_id, team_id, text)

    return {
        "response_type": "ephemeral",
        "text": "Working on it — I'll DM you shortly.",
    }


@router.post("/slack/actions")
async def slack_actions(request:Request,background_tasks: BackgroundTasks):
    raw_body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if timestamp is None or signature is None:
            raise HTTPException(status_code=401, detail="Missing Slack signature headers")
    
    slack_instance = SlackSignatureVerifier(settings.slack_signing_secret)

    try:
        slack_instance.verify(timestamp, signature, raw_body)
    except StaleSlackRequestError as e:
            raise HTTPException(status_code=401, detail=f"Stale Slack Request Error : {e}")
    except InvalidSlackSignatureError as e:
            raise HTTPException(status_code=401, detail=f"Invalid Slack Signature Error : {e}")

    formObj = await request.form()
    formPayload=formObj.get("payload")
    data=json.loads(formPayload)
    value = data["actions"][0]["value"]
    bokking=json.loads(value)
    user_id=bokking['user_id']
    team_id=bokking['team_id']
    acting_email=bokking['acting_email']
    attendee_emails=bokking['attendee_emails']
    start=datetime.fromisoformat(bokking['start'])
    end=datetime.fromisoformat(bokking['end'])

    background_tasks.add_task(handle_book_slot, user_id, team_id, acting_email, attendee_emails, start, end)

    return {"ok": True}



    
    


    



