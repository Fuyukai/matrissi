import attr

from matriisi.dataclasses.message import Message
from matriisi.dataclasses.room import Room
from matriisi.robotics.event.base import Event


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
