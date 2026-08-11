from datetime import datetime, timedelta
from backend.integrations.calendar_provider import BusySlot

def find_free_slots(
    busy_by_person: dict[str, list[BusySlot]],
    search_start: datetime,
    search_end: datetime,
    duration_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """
    Merges all busy blocks across all attendees, returns gaps
    >= duration_minutes within the search window.
    """
    all_busy: list[BusySlot] = []
    for slots in busy_by_person.values():
        all_busy.extend(slots)

    # sort by start time
    all_busy.sort(key=lambda s: s.start)

    # merge overlapping/adjacent blocks
    merged: list[BusySlot] = []
    for slot in all_busy:
        if merged and slot.start <= merged[-1].end:
            merged[-1] = BusySlot(
                start=merged[-1].start,
                end=max(merged[-1].end, slot.end),
            )
        else:
            merged.append(BusySlot(start=slot.start, end=slot.end))

    # find gaps >= duration
    free: list[tuple[datetime, datetime]] = []
    cursor = search_start
    for busy in merged:
        gap_end = busy.start
        if (gap_end - cursor) >= timedelta(minutes=duration_minutes):
            free.append((cursor, gap_end))
        cursor = max(cursor, busy.end)

    # check gap after last busy block
    if (search_end - cursor) >= timedelta(minutes=duration_minutes):
        free.append((cursor, search_end))

    return free