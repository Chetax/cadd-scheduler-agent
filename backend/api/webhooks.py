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
from zoneinfo import ZoneInfo

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
    """
    Does all the slow work — email lookup, onboarding check, calendar
    calls — AFTER Slack has already gotten its immediate acknowledgment.
    Any result (auth link or meeting confirmation) is delivered via DM,
    since the original HTTP response is long gone by the time this runs.
    """
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
    attendee_emails = []

    for mentioned_user_id in mention_ids:
        email = user_info_provider.get_email(mentioned_user_id)

        if email:
            attendee_emails.append(email)
            
    provider = GoogleCalendarProvider(creds)

    provider.get_availability(
        user_ids=[acting_email] + attendee_emails,
        date=datetime.now(timezone.utc),
    )

    timezone_str = "Asia/Kolkata"
    now = datetime.now(ZoneInfo(timezone_str))

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


    meeting = provider.create_meeting(
        organizer_id=acting_email,
        attendee_ids=attendee_emails,
        start=start,
        end=end,
        title="Meeting scheduled via cadd",
    )

    slack_client.chat_postMessage(
        channel=user_id,
        text=f"✅ Meeting scheduled! Join here: {meeting.join_url}\n🕒 {meeting.start} → {meeting.end}",
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

    # Schedule the slow work to run AFTER this response is sent.
    background_tasks.add_task(process_cadd_command, user_id, team_id, text)

    # Respond to Slack immediately — well under the 3-second window.
    return {
        "response_type": "ephemeral",
        "text": "Working on it — I'll DM you shortly.",
    }