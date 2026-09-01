# scripts/test_request_parser.py
from datetime import datetime
from zoneinfo import ZoneInfo
from backend.core.config import settings
from backend.integrations.bedrock.request_parser import BedrockRequestParser

parser = BedrockRequestParser(settings.bedrock_model_id, settings.aws_region)
now = datetime.now(ZoneInfo("Asia/Kolkata"))

phrases = [
    "meet with @mohit tomorrow at 3pm",     # expect: BOOK, exact
    "is @ankit free at 12?",                 # expect: CHECK, exact
    "what's on my calendar today?",          # expect: MY_CALENDAR, time=None
    "meet with @ashwin eod",                 # expect: BOOK, vague
]

for phrase in phrases:
    result = parser.understand(phrase, now=now, timezone="Asia/Kolkata")
    print(f"{phrase!r} -> {result}")