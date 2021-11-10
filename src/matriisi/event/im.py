import attr
from trio.lowlevel import checkpoint

from matriisi.dataclasses.message import Message
from matriisi.dataclasses.room import Room
from matriisi.event.base import Event
from matriisi.http import MatrixEventRoomMessage


@attr.s(frozen=True, slots=True)
class MessageEvent(Event):
    """
    Event for when a message is received.
    """

    insignificant = False

    #: The snapshot of the room the message event was received in.
    room: Room = attr.ib()

    #: The message object for this event.
    content: Message = attr.ib()


@attr.s(frozen=True, slots=True)
class MessageReplyEvent(MessageEvent):
    """
    Event for when a message is replied to.
    """

    async def replied_to_message(self) -> Message:
        """
        Gets the message that was replied to.
        """
        client = self.room._client

        for evt in client.state.cached_events:
            if evt.event_id == self.content.event.content.relates_to.replying_to:
                await checkpoint()
                return Message(evt, self.room)

        event = await client.http_client.get_single_event(
            room_id=self.room.id,
            event_id=self.content.event.content.relates_to.replying_to,
            event_type=MatrixEventRoomMessage,
        )

        return Message(event, self.room)
