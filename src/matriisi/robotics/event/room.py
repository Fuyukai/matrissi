from __future__ import annotations

import attr

from matriisi.dataclasses.member import RoomMember
from matriisi.dataclasses.room import JoinedRoom
from matriisi.identifier import Identifier
from matriisi.robotics.event.base import Event

__all__ = (
    "RoomJoinedEvent",
    "RoomMemberJoinedEvent",
)


@attr.s(frozen=True, slots=True)
class RoomJoinedEvent(Event):
    """
    Fired when a room is joined by the current user.
    """

    insignificant = False

    #: The room being joined.
    room: JoinedRoom = attr.ib()


@attr.s(frozen=True, slots=True)
class RoomMemberJoinedEvent(Event):
    """
    Fires when a room is joined by any user.
    """

    insignificant = False

    #: The room being joined.
    room: JoinedRoom = attr.ib()

    #: The ID of the member joining.
    member_id: Identifier = attr.ib()

    @property
    def member(self) -> RoomMember:
        """
        :return: The member object for this event.
        """

        return self.room.member(self.member_id)
