"""no
backend/integrations/bedrock/request_parser.py

Bedrock-backed implementation of the RequestParser contract.

Classifies a Slack message into Intent + Confidence and, when relevant,
resolves a concrete time — in one Converse API call, so /cadd stays as fast
as the single-call TimeParser was. Sealed the same way as BedrockTimeParser:
a valid ParsedRequest out, or TimeParseError raised. Nothing fuzzy leaks to
callers.
"""
import json
from datetime import datetime
import boto3
from backend.core.time_parser import ParsedTime, TimeParseError
from backend.core.request_parser import RequestParser, ParsedRequest, Intent, Confidence


class BedrockRequestParser(RequestParser):

    def __init__(self, model_id: str, region: str = "us-east-1"):
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    def understand(self, text: str, *, now: datetime, timezone: str) -> ParsedRequest:
        system_instruction = """Convert the message to JSON describing what the user wants.

        Return only JSON with no prose and no markdown fences.
        The exact shape is:
        '{"intent": "book" | "check" | "my_calendar", "confidence": "exact" | "vague", "start": "<ISO 8601 with the user's timezone offset>" | null, "duration_minutes": <int> | null}'

        INTENT — pick exactly one:
        - "book": user wants to schedule/create a meeting. e.g. "meet with @mohit tomorrow at 3pm", "set up a call with @ashwin".
        - "check": user is asking whether someone is free/busy, NOT asking to book. e.g. "is @ankit free at 12?", "is @mohit busy tomorrow evening?".
        - "my_calendar": user is asking about their OWN schedule, no attendee involved. e.g. "what's on my calendar today?", "am I free at 5?".

        CONFIDENCE — pick exactly one:
        - "exact": the phrase names a specific clock time or a clearly computable one. e.g. "3pm", "tomorrow at 3", "in 2 hours".
        - "vague": the phrase names a fuzzy or shorthand time that needs resolving before use. e.g. "eod", "sometime this afternoon", "later today".

        TIME FIELDS:
        - If intent is "my_calendar" and no specific time is stated, set both "start" and "duration_minutes" to null.
        - Otherwise, resolve "start" against the current time you'll be given. Stated time is the START, not the end.
        - If the phrase gives an explicit end time or range, set duration_minutes from the gap between start and end.
        - Default duration_minutes to 30 if a time is given but no duration/end is stated.

        Always return all four keys. Use null for start/duration_minutes only when genuinely not applicable (see TIME FIELDS above) — never omit keys.
        """

        user_message = (
            f"Current time: {now.isoformat()} ({timezone})\n"
            f"User's timezone: {timezone}\n"
            f"Phrase: {text!r}"
        )

        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system_instruction}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"temperature": 0, "maxTokens": 200},
        )

        data = response["output"]["message"]["content"][0]["text"].strip()

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise TimeParseError(f"model returned non-JSON: {data!r}") from e

        try:
            intent = Intent(parsed["intent"])
            confidence = Confidence(parsed["confidence"])
        except (KeyError, ValueError) as e:
            raise TimeParseError(f"model returned unrecognized intent/confidence: {parsed!r}") from e

        time = None
        if parsed.get("start") is not None:
            time = ParsedTime(
                start=datetime.fromisoformat(parsed["start"]),
                duration_minutes=int(parsed["duration_minutes"]),
            )

        return ParsedRequest(intent=intent, confidence=confidence, time=time)