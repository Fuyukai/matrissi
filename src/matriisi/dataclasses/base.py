from __future__ import annotations

from typing import Generic, TypeVar

import attr

from matriisi.http import MatrixHttpEventContent, MatrixRoomBaseEvent

_EVT_T = TypeVar("_EVT_T", bound=MatrixHttpEventContent)


@attr.s(frozen=True, slots=True)
class EventWrapper(Generic[_EVT_T]):
    """
    Base class for a dataclass that wraps a *single* event.
    """

    #: The event that this object wraps, for example an ``m.room.member`` event.
    event: MatrixRoomBaseEvent[_EVT_T] = attr.ib()
