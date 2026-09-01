"""
backend/core/request_parser.py

Contract for turning a Slack message into a structured request: what the
user wants to do (Intent), how sure the model is (Confidence), and — when
relevant — a concrete time. Extends the TimeParser idea (Session 6) to cover
intent, so "is @Ankit free?" stops being treated as a booking request.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from enum import Enum
from backend.core.time_parser import ParsedTime, TimeParseError


class Intent(str, Enum):
    BOOK = "book"
    CHECK = "check"
    MY_CALENDAR = "my_calendar"


class Confidence(str, Enum):
    EXACT = "exact"
    VAGUE = "vague"


@dataclass(frozen=True)
class ParsedRequest:
    intent: Intent
    confidence: Confidence
    time: Optional[ParsedTime] = None


class RequestParser(ABC):
    @abstractmethod
    def understand(self, text: str, *, now: datetime, timezone: str) -> ParsedRequest:
        """Classify intent and, when relevant, resolve a concrete time.

        Returns a ParsedRequest whose time is set for BOOK (and CHECK, when a
        time is stated) and None for MY_CALENDAR. Raises TimeParseError if the
        request can't be understood at all."""
        ...