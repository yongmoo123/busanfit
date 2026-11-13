"""Validate normalized weekday intervals; never parse display text as evidence."""
from datetime import datetime, time, timedelta, timezone

from app.domain.place import PlaceRecord, WEEKDAY_KEYS, validate_open_hours

SEOUL = timezone(timedelta(hours=9))


def opening_windows(place: PlaceRecord, start: datetime, end: datetime):
    parsed = place.open_hours.parsed
    if parsed is None:
        return (), False
    try:
        validate_open_hours(parsed)
    except ValueError:
        return (), False
    day = start.astimezone(SEOUL).date()
    known_day = WEEKDAY_KEYS[day.weekday()] in parsed
    spans = []
    # A previous day's overnight opening can cover the beginning of this day.
    for date in (day - timedelta(days=1), day):
        for interval in parsed.get(WEEKDAY_KEYS[date.weekday()], ()):
            opening = datetime.combine(date, time.fromisoformat(interval['open']), SEOUL)
            if interval['close'] == '24:00':
                closing = datetime.combine(date + timedelta(days=1), time(), SEOUL)
            else:
                closing = datetime.combine(date, time.fromisoformat(interval['close']), SEOUL)
                if closing < opening:
                    closing += timedelta(days=1)
            if opening < end and closing > start:
                spans.append((opening, closing))
    merged = []
    for opening, closing in sorted(spans):
        if merged and opening <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(closing, merged[-1][1]))
        else:
            merged.append((opening, closing))
    return tuple(merged), known_day


def find_slot(place: PlaceRecord, arrival: datetime, deadline: datetime, minutes: int):
    spans, _ = opening_windows(place, arrival, deadline)
    for opening, closing in spans:
        start = max(arrival, opening)
        # Wire summaries are integer minutes. Round arrivals forward (never
        # shorten a stay or move outside the user's window).
        if start.second or start.microsecond:
            start = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
        finish = start + timedelta(minutes=minutes)
        if finish <= min(closing, deadline):
            return start, finish
    return None


def covers(place: PlaceRecord, start: datetime, end: datetime):
    spans, known = opening_windows(place, start, end)
    return any(opening <= start and end <= closing for opening, closing in spans), known
