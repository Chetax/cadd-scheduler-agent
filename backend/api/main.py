"""
backend/api/main.py

FastAPI application entrypoint.

Wires the Slack webhook router and serves the OAuth callback that completes
AgentCore's USER_FEDERATION flow. Startup config (logging, clients) lives
here; request handling lives in webhooks.py.
"""

import boto3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import uvicorn
from backend.core.logging import setup_logging, get_logger

from backend.core.config import settings
from backend.api.webhooks import router
from backend.integrations.dynamodb.pending_session_repository import (
    DynamoDBPendingSessionRepository,
)
from backend.integrations.dynamodb.user_repository import DynamoDBUserRepository

setup_logging()
logger = get_logger(__name__)

app = FastAPI()
app.include_router(router)

agentcore = boto3.client("bedrock-agentcore", region_name=settings.aws_region)
pending_sessions = DynamoDBPendingSessionRepository()
user_repo = DynamoDBUserRepository()
slack = WebClient(token=settings.slack_bot_token)


def _html(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif;padding:2rem'>"
        f"<h2>{title}</h2><p>{body}</p></body></html>",
        status_code=status,
    )


@app.get("/oauth2/callback")
async def oauth2_callback(request: Request):
    session_id = request.query_params.get("session_id")
    if not session_id:
        logger.warning("callback hit without session_id")
        return _html("Missing session", "No session_id in the callback URL.", status=400)

    popped = pending_sessions.pop(session_id)

    if popped is None:
        logger.warning("no pending session found for session_id=%s", session_id)
        return _html(
            "Session expired",
            "This onboarding link has already been used or has expired. "
            "Please run <code>/cadd</code> in Slack again.",
            status=410,
        )

    logger.info(
        "callback: session_id=%s agentcore_user_id=%s slack_user_id=%s",
        session_id, popped.agentcore_user_id, popped.slack_user_id,
    )
    try:
        agentcore.complete_resource_token_auth(
            sessionUri=session_id,
            userIdentifier={"userId": popped.agentcore_user_id},
        )
    except Exception:
        logger.exception("complete_resource_token_auth failed")
        return _html(
            "Something went wrong",
            "We couldn't finish connecting your Google Calendar. "
            "Please run <code>/cadd</code> in Slack again.",
            status=500,
        )

    try:
        user_repo.mark_authorized(popped.slack_user_id)
    except Exception:
        logger.exception(
            "mark_authorized failed for slack_user_id=%s — vault is bound but DB state is stale",
            popped.slack_user_id,
        )

    try:
        slack.chat_postMessage(
            channel=popped.slack_user_id,
            text="Google Calendar connected. You can now use `/cadd` to schedule meetings.",
        )
    except SlackApiError:
        logger.exception("slack DM failed for slack_user_id=%s", popped.slack_user_id)

    return _html(
        "All set ",
        "Your Google Calendar is connected. You can close this tab and head back to Slack.",
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=settings.app_port)