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
from datetime import datetime, timedelta, timezone
from backend.integrations.bedrock.time_parser import BedrockTimeParser, TimeParseError
import re
from backend.core.availability import find_free_slots
from zoneinfo import ZoneInfo
from backend.core.logging import get_logger

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

    timezone_str = "Asia/Kolkata"
    now = datetime.now(ZoneInfo(timezone_str))
    ist = ZoneInfo(timezone_str)

    try:
        parsed = time_parser.parse(text, now=now, timezone=timezone_str)
    except TimeParseError:
        slack_client.chat_postMessage(
            channel=user_id,
            text="I couldn't understand that time — try something like 'tomorrow at 3pm'.",
        )
        return

    start = parsed.start
    end = parsed.start + timedelta(minutes=parsed.duration_minutes)

    logger.info(f"Querying slot: {start} → {end} for {[acting_email] + attendee_emails}")

    start_ist = start.astimezone(ist)
    if start_ist.hour < 3 or (start_ist.hour == 2 and start_ist.minute <= 30):
        # e.g. 12:00 AM on Aug 14 → working window started Aug 13 5:30 PM
        query_start = (start_ist - timedelta(days=1)).replace(hour=17, minute=30, second=0, microsecond=0)
    else:
        query_start = start_ist.replace(hour=17, minute=30, second=0, microsecond=0)
    query_end = query_start + timedelta(hours=9)

    busy_by_person = provider.get_availability(
        user_ids=[acting_email] + attendee_emails,
        start=query_start,
        end=query_end,
    )

    logger.info(f"Busy results: {busy_by_person}")

    conflicts = {
        email: slots
        for email, slots in busy_by_person.items()
        if slots
    }

    if conflicts:
        # same midnight-crossing logic as query window above
        if start_ist.hour < 3 or (start_ist.hour == 2 and start_ist.minute <= 30):
            work_start = (start_ist - timedelta(days=1)).replace(hour=17, minute=30, second=0, microsecond=0)
        else:
            work_start = start_ist.replace(hour=17, minute=30, second=0, microsecond=0)
        work_end = work_start + timedelta(hours=9)
        search_start = work_start

        free_slots = find_free_slots(
            busy_by_person=busy_by_person,
            search_start=search_start,
            search_end=work_end,
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

            slot_lines = "\n".join(
                f"  {i+1}. {s.astimezone(ist).strftime('%I:%M %p')} – "
                f"{e.astimezone(ist).strftime('%I:%M %p')} IST "
                f"({format_duration(s, e)})"
                for i, (s, e) in enumerate(free_slots[:3])
            )
            slack_client.chat_postMessage(
                channel=user_id,
                text=(
                    f"❌ {who} at {start.astimezone(ist).strftime('%I:%M %p IST')}\n\n"
                    f"📅 Free windows:\n{slot_lines}\n\n"
                    f"_Pick a slot — buttons coming next session..._"
                ),
            )
        else:
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"❌ {who} at {start.astimezone(ist).strftime('%I:%M %p IST')}\n\nNo free slots in working hours.",
            )
        return

    # no conflicts — book it
    # meeting = provider.create_meeting(
    #     organizer_id=acting_email,
    #     attendee_ids=attendee_emails,
    #     start=start,
    #     end=end,
    #     title="Meeting scheduled via cadd",
    # )

    # logger.info(f"Meeting created: {meeting.join_url}")
    slack_client.chat_postMessage(
        channel=user_id,
        text=(
        f"✅ No conflicts found!\n"
        f"🕒 Slot: {start.astimezone(ist).strftime('%I:%M %p')} – "
        f"{end.astimezone(ist).strftime('%I:%M %p')} IST\n"
        f"👥 Attendees: {', '.join(attendee_display.values())}\n"
        f"_(Meeting creation is disabled for testing)_"
    ),
        # text=f"✅ Meeting scheduled! Join here: {meeting.join_url}\n🕒 {meeting.start} → {meeting.end}",
    )


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