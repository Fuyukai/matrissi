from __future__ import annotations

import attr

from matriisi.dataclasses.room import Room
from matriisi.robotics.event.base import Event

__all__ = ("RoomJoinedEvent",)


@attr.s(frozen=True, slots=True)
class RoomJoinedEvent(Event):
    """
    Fired when a room is joined by the current user.
    """

    insignificant = False

    #: The room being joined.
    room: Room = attr.ib()
