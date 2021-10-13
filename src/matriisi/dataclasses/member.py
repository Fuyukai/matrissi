from __future__ import annotations

from typing import TYPE_CHECKING

from matriisi.http.httpevents import MatrixEventRoomMember, MatrixRoomStateEvent
from matriisi.identifier import Identifier

if TYPE_CHECKING:
    from matriisi.dataclasses.room import Room
    from matriisi.robotics.roboclient import RoboClient


class RoomMember(object):
    """
    A single member in a single room.
    """

    def __init__(
        self, client: RoboClient, room: Room, event: MatrixRoomStateEvent[MatrixEventRoomMember]
    ):
        """
        :param client: The :class:`.RoboClient` this member was found using.
        :param id: The :class:`.Identifier` for the user.
        :param room: The :class:`.Room` this member is in.
        """

        self._client = client

        #: The Matrix event for this member.

        #: The room this member is in.
        self.room = room

    @property
    def event(self) -> MatrixRoomStateEvent[MatrixEventRoomMember]:
        """
        :return: The event that defined this member.
        """
        evt = self.room.find_event("m.room.member", str(self.id), MatrixEventRoomMember)
        assert evt, "room is missing event for this member?"

        return evt

    @property
    def display_name(self) -> str:
        """
        Gets the display name for this user.
        """
        event = self.room.find_event("m.room.member", str(self.id), MatrixEventRoomMember)
        assert event, "room is missing event for this member"

        dn = event.content.display_name
        if dn is None:
            return str(self.id)

        # make sure the dn is unique
        unique = (
            sum(
                1
                for evt in self.room.find_all_events(
                    "m.room.member", content_type=MatrixEventRoomMember
                )
                if evt.content.display_name == event.content.display_name
            )
            == 1
        )

        if unique:
            return dn
        else:
            return f"{dn} ({self.id})"
