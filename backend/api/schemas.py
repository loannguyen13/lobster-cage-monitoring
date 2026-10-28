"""Validated query contracts and bounded history requests."""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import BaseModel


class Acknowledgment(BaseModel):
    id: int
    acknowledged_at: datetime
    acknowledged_by: str


def time_range(start, end):
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=1)
    if start.utcoffset() is None or end.utcoffset() is None:
        raise HTTPException(422, 'from/to must include a timezone')
    if not timedelta(0) < end - start <= timedelta(days=7):
        raise HTTPException(422, 'Time range must be positive and at most seven days')
    return start, end
