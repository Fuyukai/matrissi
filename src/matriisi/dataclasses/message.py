from __future__ import annotations

from typing import TYPE_CHECKING

import attr

from matriisi.dataclasses.base import EventWrapper
from matriisi.http import MatrixEventRoomMessage
from matriisi.identifier import Identifier

if TYPE_CHECKING:
    from matriisi.dataclasses.room import JoinedRoom
    from matriisi.robotics.roboclient import RoboClient


@attr.s(frozen=True, slots=True)
class Message(EventWrapper[MatrixEventRoomMessage]):
    """
    Wraps a single ``m.room.message`` event/
    """

    _client: RoboClient = attr.ib()

    #: The room this message was sent in.
    room: JoinedRoom = attr.ib()

    @property
    def sender_id(self) -> Identifier:
        """
        :returns: The ID of the sender for this message.
        """

        return self.event.sender

    @property
    def raw_content(self) -> str:
        """
        :return: The raw content for this message.
        """

        return self.event.content.body
