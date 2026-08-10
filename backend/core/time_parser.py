"""
Abstract contract for turning a natural-language meeting-time phrase (e.g. 'tomorrow at 3pm')
into a concrete, timezone-aware start time and duration. 
"""

from dataclasses import dataclass
from datetime import datetime
from abc import ABC,abstractmethod

@dataclass
class ParsedTime:
    """The resolved output of parsing a time phrase. start is timezone-aware; duration_minutes is the meeting length."""
    start:datetime
    duration_minutes:int 

class TimeParseError(Exception):
    """Raised when a phrase cannot be resolved to a concrete time."""
     
    
class TimeParser(ABC):

    @abstractmethod
    def parse(self, text: str, *, now: datetime, timezone: str) -> ParsedTime:
        """Resolve text into a concrete time, interpreting relative phrases against now and the user's timezone.
          Returns a ParsedTime whose start is timezone-aware. Raises TimeParseError if the phrase can't be resolved."""



