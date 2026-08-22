"""
backend/core/org_profile.py

Org and shift configuration.

Shift owns working hours and the arithmetic they imply — including which
calendar day a shift belongs to when it crosses midnight. OrgProfile owns
what's company-wide: timezone and default meeting length.

Hours live on Shift, not OrgProfile, because one org can run several shifts.
"""


from datetime import time ,datetime,timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict

class Shift(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    work_start: time
    work_end: time

    def working_window(self, moment: datetime, tz: ZoneInfo) -> tuple[datetime, datetime]:
        moment = moment.astimezone(tz)

        if self.work_end >= self.work_start:
            start_date = moment.date()
            end_date = moment.date()
        elif moment.time() < self.work_end:
            start_date = moment.date() - timedelta(days=1)
            end_date = moment.date()
        else:
            start_date = moment.date()
            end_date = moment.date() + timedelta(days=1)

        return (
            datetime.combine(start_date, self.work_start, tzinfo=tz),
            datetime.combine(end_date, self.work_end, tzinfo=tz),
        )


class OrgProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    org_id: str
    timezone: str
    default_duration_minutes: int = 30

    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
