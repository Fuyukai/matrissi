from __future__ import annotations

from typing import TYPE_CHECKING

import attr

from matriisi.dataclasses.base import EventWrapper
from matriisi.http import MatrixEventRoomMember
from matriisi.identifier import Identifier

if TYPE_CHECKING:
    from matriisi.dataclasses.room import Room


@attr.s(slots=True)
class RoomMember(EventWrapper[MatrixEventRoomMember]):
    """
    A single member in a single room.
    """

    #: The room this member is in.
    room: Room = attr.ib()

    @property
    def id(self) -> Identifier:
        """
        :return: The :class:`.Identifier` for this member.
        """
        return self.event.sender

    @property
    def display_name(self) -> str:
        """
        :return: The calculated display name for this member.
        """
        dn = self.event.content.display_name
        if dn is None:
            return str(self.id)

        # make sure the dn is unique
        unique = (
            sum(
                1
                for evt in self.room.find_all_events(
                    "m.room.member", content_type=MatrixEventRoomMember
                )
                if evt.content.display_name == self.event.content.display_name
            )
            == 1
        )

        if unique:
            return dn
        else:
            return f"{dn} ({self.id})"
