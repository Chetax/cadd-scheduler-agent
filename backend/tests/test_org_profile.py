from datetime import time,datetime
from zoneinfo import ZoneInfo
from backend.core.org_profile import Shift

IST=ZoneInfo("Asia/Kolkata")


late = Shift(name="late", work_start=time(17, 30), work_end=time(2, 30))
mid = Shift(name="mid", work_start=time(12, 0), work_end=time(21, 0))

def test_midnight_belongs_to_previous_evening():
    moment = datetime(2026, 8, 14, 0, 0, tzinfo=IST)
    start, end = late.working_window(moment, IST)
    assert start == datetime(2026, 8, 13, 17, 30, tzinfo=IST)
    assert end == datetime(2026, 8, 14, 2, 30, tzinfo=IST)

def test_evening_belongs_to_same_day():
    moment = datetime(2026, 8, 14, 20, 0, tzinfo=IST)
    start, end = late.working_window(moment, IST)
    assert start == datetime(2026, 8, 14, 17, 30, tzinfo=IST)
    assert end == datetime(2026, 8, 15, 2, 30, tzinfo=IST)


def test_non_crossing_shift_never_rolls_back():
    moment = datetime(2026, 8, 14, 14, 0, tzinfo=IST)
    start, end = mid.working_window(moment, IST)
    assert start == datetime(2026, 8, 14, 12, 0, tzinfo=IST)
    assert end == datetime(2026, 8, 14, 21, 0, tzinfo=IST)

