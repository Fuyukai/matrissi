from __future__ import annotations

from typing import TYPE_CHECKING, Union

import attr

from matriisi.dataclasses.base import EventWrapper
from matriisi.http import MatrixEventRoomMessage

if TYPE_CHECKING:
    from matriisi.dataclasses.member import RoomMember
    from matriisi.identifier import Identifier
    from matriisi.dataclasses.room import Room


@attr.s(frozen=True, slots=True)
class Message(EventWrapper[MatrixEventRoomMessage]):
    """
    Wraps a single ``m.room.message`` event/
    """

    #: The room this message was sent in.
    room: Room = attr.ib()

    async def edit_text(
        self,
        new_content: str,
        *,
        render_markdown: bool = True,
        wait_for_sync: bool = False,
        **extra,
    ) -> Union[str, Message]:
        """
        Edits this message. You must have been the one who sent it.
        """

        return await self.room.edit_text_message(
            self.event.event_id,
            new_content,
            render_markdown=render_markdown,
            wait_for_sync=wait_for_sync,
            **extra,
        )

    def is_notice(self) -> bool:
        """
        :return: If this message is a notice message.
        """

        return self.event.content.type == "m.notice"

    @property
    def sender_id(self) -> Identifier:
        """
        :return: The ID of the sender for this message.
        """

        return self.event.sender

    @property
    def sender(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` of this member.
        """

        evt = self.room.member(self.sender_id)
        assert evt, f"room has non-existent sender {self.sender_id}?"
        return evt

    @property
    def raw_content(self) -> str:
        """
        :return: The raw content for this message.
        """

        return self.event.content.body
