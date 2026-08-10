"""
Bedrock-backed implementation of the TimeParser contract.

Turns a natural-language meeting-time phrase (e.g. "tomorrow at 3pm") into a
concrete, timezone-aware ParsedTime by calling a Bedrock model via the Converse
API. The model is instructed to return strict JSON; this class parses that JSON
and enforces the contract — a valid ParsedTime out, or TimeParseError raised.
The LLM's non-determinism is sealed entirely inside parse(); nothing fuzzy
leaks to callers.
"""
import json
from datetime import datetime
import boto3
from backend.core.time_parser import (
    TimeParser,
    ParsedTime,
    TimeParseError,
)


class BedrockTimeParser(TimeParser):

    def __init__(self, model_id: str, region: str = "us-east-1"):
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id

    def parse(self, text: str, *, now: datetime, timezone: str) -> ParsedTime:
        """Resolve text into a concrete time, interpreting relative phrases against now and the user's timezone.
        Returns a ParsedTime whose start is timezone-aware. Raises TimeParseError if the phrase can't be resolved."""

        system_instruction = """Convert the phrase to JSON.
Return only JSON with no prose and no markdown fences.
The exact shape is {"start": "<ISO 8601 with UTC offset>", "duration_minutes": <int>}.
Resolve relative phrases against the current time you'll be given.
Default duration to 30 if unstated.
If the phrase has no usable time, return {"error": "<reason>"} instead.

NOTE: 
- stated time is the START
- If the phrase gives an explicit end time or range, set duration from the gap between start and end.

"""

        user_message = (
            f"Current time: {now.isoformat()} ({timezone})\n"
            f"Phrase: {text!r}"
        )

        response = self._client.converse(
            modelId=self._model_id,
            system=[{"text": system_instruction}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 200,
            },
        )

        data = response["output"]["message"]["content"][0]["text"].strip()

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise TimeParseError(f"model returned non-JSON: {data!r}") from e

        if "error" in parsed:
            raise TimeParseError(parsed["error"])

        return ParsedTime(
            start=datetime.fromisoformat(parsed["start"]),
            duration_minutes=int(parsed["duration_minutes"]),
        )