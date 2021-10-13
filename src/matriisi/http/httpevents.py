from __future__ import annotations

import enum
from typing import Generic, List, Optional, TypeVar, Union

import attr

from matriisi.identifier import Identifier

__all__ = (
    "MatrixHttpEvent",
    "MatrixRoomEvent",
    "MatrixRoomStateEvent",
    "MatrixHttpEventContent",
    "MatrixUnknownEventContent",
    "MatrixEventRoomCreate",
    "MatrixEventRoomMember",
    "MatrixEventRoomMessage",
    "MatrixRoomMemberMembership",
    "MatrixEventRoomCreatePreviousRoom",
    "MatrixRoomBaseStateEvent",
    "MatrixRoomBaseEvent",
    "MatrixEventRoomCanonicalAlias",
    "MatrixEventRoomName",
    "MatrixRoomJoinRule",
    "MatrixEventRoomJoinRules",
    "MatrixEventRoomTopic",
)

CONTENT_TYPE = TypeVar("CONTENT_TYPE")


@attr.s(frozen=True, slots=True)
class MatrixHttpEventContent:
    """
    The base class for known event contents.
    """

    pass


@attr.s(frozen=True, slots=True)
class MatrixUnknownEventContent(MatrixHttpEventContent):
    """
    Class used when an event is unknown.
    """

    data: dict = attr.ib()


@attr.s(frozen=True, slots=False)
class MatrixHttpEvent(Generic[CONTENT_TYPE]):
    """
    The base class for events returned over the ``/sync`` endpoint.
    """

    #: The type key for this event.
    type: str = attr.ib()

    #: The content of this event. Polymorphic.
    content: CONTENT_TYPE = attr.ib()


@attr.s(frozen=True, slots=False)
class MatrixRoomBaseEvent(MatrixHttpEvent[CONTENT_TYPE]):
    """
    Base event for any event in a room.
    """

    #: The sender for this event.
    sender: Identifier = attr.ib(converter=Identifier.parse)


@attr.s(frozen=True, slots=False)
class MatrixRoomBaseStateEvent(MatrixRoomBaseEvent[CONTENT_TYPE]):
    """
    Base event that a state event is guarenteed to have. This is used for StrippedState events.
    """

    #: The state_key for this event.
    state_key: str = attr.ib()


@attr.s(frozen=True, slots=False)
class MatrixRoomEvent(MatrixRoomBaseEvent[CONTENT_TYPE]):
    """
    Structure for known room events.
    """

    #: The globally unique event ID.
    event_id: str = attr.ib()

    #: The origin server timestamp, in milliseconds.
    origin_timestamp: int = attr.ib()

    #: The room ID for the event.
    room_id: Identifier = attr.ib(converter=Identifier.parse)


# can't be slotted due to multi-inheritance...
@attr.s(frozen=True, slots=False)
class MatrixRoomStateEvent(MatrixRoomEvent[CONTENT_TYPE], MatrixRoomBaseStateEvent[CONTENT_TYPE]):
    """
    Structure for state events.
    """

    #: The previous conteent for this event. Optional.
    prev_content: Optional[CONTENT_TYPE] = attr.ib(default=None)


## Known event content types
@attr.s(frozen=True, slots=True)
class MatrixEventRoomCreatePreviousRoom(MatrixHttpEventContent):
    #: The last known event ID for the previous room.
    event_id: str = attr.ib()

    #: The ID of the old room.
    room_id: Identifier = attr.ib(converter=Identifier.parse)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomCreate(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.create`` event.
    """

    #: The creator of this room.
    creator: Identifier = attr.ib(converter=Identifier.parse)

    #: If users on other serveers can join this room.
    m_federate: bool = attr.ib(default=True)

    #: A reference to the previous room.
    predecessor: Optional[MatrixEventRoomCreatePreviousRoom] = attr.ib(default=None)

    #: The room version of this room.
    room_version: str = attr.ib(default="1")


class MatrixRoomMemberMembership(enum.Enum):
    """
    Enumeration of possible values for the membership state in an ``m.room.member`` event.
    """

    INVITE = "invite"
    JOIN = "join"
    KNOCK = "knock"
    LEAVE = "leave"
    BAN = "ban"


@attr.s(frozen=True, slots=True)
class MatrixEventRoomMember(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.member`` event.
    """

    #: The membership state for this event.
    membership: MatrixRoomMemberMembership = attr.ib(converter=MatrixRoomMemberMembership)

    #: The avatar URL for the member.
    avatar_url: Optional[str] = attr.ib(default=None)

    # actual JSON name: displayname
    #: The display name for the member.
    display_name: Optional[str] = attr.ib(default=None)

    #: The reason for why membership has changed.
    reason: Optional[str] = attr.ib(default=None)

    is_direct: bool = attr.ib(default=False)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomMessage(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.message`` event.
    """

    #: The textual representation of this message.
    body: str = attr.ib()

    #: The type of this message.
    type: str = attr.ib()

    #: The extra, specific data for this message.
    extra_data: dict = attr.ib(factory=dict)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomCanonicalAlias(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.canonical_alias`` event.
    """

    #: The canonical alias for this room.
    alias: Optional[str] = attr.ib()

    #: The list of alternative aliases for this room.
    alt_aliases: List[str] = attr.ib(factory=list)


class MatrixRoomJoinRule(enum.Enum):
    """
    Enumeration of possible join rules.
    """

    PUBLIC = "public"
    KNOCK = "knock"
    INVITE = "invite"
    PRIVATE = "private"


@attr.s(frozen=True, slots=True)
class MatrixEventRoomJoinRules(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.join_rules`` event.
    """

    #: The join rule for this event.
    join_rule: MatrixRoomJoinRule = attr.ib(converter=MatrixRoomJoinRule)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomName(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.name`` event.
    """

    #: The name of this room.
    name: str = attr.ib()


@attr.s(frozen=True, slots=True)
class MatrixEventRoomTopic(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.topic`` event.
    """

    #: The room's topic text.
    topicc: str = attr.ib()
