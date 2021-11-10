from __future__ import annotations

from typing import Optional

import attr

from matriisi.dataclasses.room import Room
from matriisi.event.base import Event, RoomEvent
from matriisi.http import MatrixRoomStateEvent

__all__ = (
    "RoomMeJoinedEvent",
    "RoomTopicChangedEvent",
    "RoomStateChangedEvent",
)


@attr.s(frozen=True, slots=True)
class RoomStateChangedEvent(Event):
    """
    Fired when a room's state changes, in any form.
    """

    insignificant = False

    #: The snapshot of the room before the state change.
    before: Room = attr.ib()

    #: The snapshot of the room after the state change.
    after: Room = attr.ib()

    #: The state event being fired.
    event: MatrixRoomStateEvent = attr.ib()


@attr.s(frozen=True, slots=True)
class RoomMeJoinedEvent(RoomEvent):
    """
    Fired when a room is joined by the current user.
    """

    insignificant = False


@attr.s(frozen=True, slots=True)
class RoomTopicChangedEvent(RoomEvent):
    """
    Fires when the topic in a room changes.
    """

    insignificant = False

    #: The previous topic.
    previous_topic: Optional[str] = attr.ib()

    #: The new topic.
    new_topic: Optional[str] = attr.ib()
