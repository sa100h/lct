from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=lambda name: _to_camel(name), populate_by_name=True)


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class EventDto(ApiModel):
    id: int
    channel_id: int
    occurred_at: datetime
    source_occurred_at: datetime
    is_alarm: bool
    value: str


class EventPage(ApiModel):
    from_: datetime = Field(alias="from")
    to: datetime
    items: list[EventDto]
    has_more: bool
    next_cursor: str | None = None


class FeedStatus(ApiModel):
    state: str
    loaded_events: int
    source_min_at: datetime
    source_max_at: datetime
    source_start_at: datetime
    source_end_at: datetime
    current_source_at: datetime
    wall_started_at: datetime
    exhausted: bool
