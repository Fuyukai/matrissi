from __future__ import annotations

import enum
from typing import Generic, List, Mapping, Optional, TypeVar

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
    "MatrixEventRoomHistoryVisibility",
    "MatrixRoomRedactedEvent",
    "MatrixRelatesTo",
    "RelatesToRelation",
    "RELATION_KEYS",
    "CONTENT_TYPE",
    "REPLY_KEYS",
)

CONTENT_TYPE = TypeVar("CONTENT_TYPE")

RELATION_KEYS = (
    "m.relations",
    "im.nheko.relations.v1.relations",
)

REPLY_KEYS = (
    "m.in_reply_to",
    "im.nheko.relations.v1.in_reply_to",
)


@attr.s(frozen=True, slots=True)
class RelatesToRelation:
    """
    A single relation between messages.
    """

    #: The relation type, e.g. "m.replaces".
    rel_type: str = attr.ib()

    #: The ID of the event this message was related to.
    event_id: str = attr.ib()

    #: The aggregration key.
    key: Optional[str] = attr.ib(default=None)


@attr.s(frozen=False, slots=True)
class MatrixRelatesTo:
    """
    Wrapper type for known 'relates to' data. Transparently wraps over both the old and new format.
    """

    # When/If 3051 is merged, strip `relates_to`.
    relations: List[RelatesToRelation] = attr.ib(factory=list)

    relates_to: Mapping[str, RelatesToRelation] = attr.ib(factory=dict)

    def for_type(self, relation: str) -> Optional[RelatesToRelation]:
        """
        Finds a relation between two messages based on the ``rel_type``.
        """

        try:
            return self.relates_to[relation]
        except KeyError:
            for k, v in self.relates_to.items():
                if k == relation:
                    return v

        return None

    @property
    def replying_to(self) -> Optional[str]:
        """
        :return: The event ID
        """

        for value in REPLY_KEYS:
            value = self.for_type(value)
            if value:
                return value.event_id

        return None


@attr.s(frozen=True, slots=True)
class MatrixHttpEventContent:
    """
    The base class for known event contents.
    """

    #: The relation data for this event.
    relates_to: MatrixRelatesTo = attr.ib(factory=MatrixRelatesTo)


@attr.s(frozen=True, slots=True)
class MatrixUnknownEventContent(MatrixHttpEventContent):
    """
    Class used when an event is unknown.
    """

    data: dict = attr.ib(kw_only=True)


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


@attr.s(frozen=True, slots=True)
class MatrixRoomRedactedEvent(MatrixRoomBaseEvent[None]):
    """
    Event class for a redacted event. This is *not* the data for an event that *causes* the
    redaction.
    """

    #: The event this event was redacted by.
    redacted_by: str = attr.ib()


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
    event_id: str = attr.ib(kw_only=True)

    #: The ID of the old room.
    room_id: Identifier = attr.ib(converter=Identifier.parse, kw_only=True)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomCreate(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.create`` event.
    """

    #: The creator of this room.
    creator: Identifier = attr.ib(converter=Identifier.parse, kw_only=True)

    #: If users on other serveers can join this room.
    m_federate: bool = attr.ib(default=True, kw_only=True)

    #: A reference to the previous room.
    predecessor: Optional[MatrixEventRoomCreatePreviousRoom] = attr.ib(default=None, kw_only=True)

    #: The room version of this room.
    room_version: str = attr.ib(default="1", kw_only=True)


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
    membership: MatrixRoomMemberMembership = attr.ib(
        converter=MatrixRoomMemberMembership, kw_only=True
    )

    #: The avatar URL for the member.
    avatar_url: Optional[str] = attr.ib(default=None, kw_only=True)

    # actual JSON name: displayname
    #: The display name for the member.
    display_name: Optional[str] = attr.ib(default=None, kw_only=True)

    #: The reason for why membership has changed.
    reason: Optional[str] = attr.ib(default=None, kw_only=True)

    is_direct: bool = attr.ib(default=False, kw_only=True)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomMessage(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.message`` event.
    """

    #: The textual representation of this message.
    body: str = attr.ib(kw_only=True)

    #: The type of this message.
    type: str = attr.ib(kw_only=True)

    #: The extra, specific data for this message.
    extra_data: dict = attr.ib(factory=dict, kw_only=True)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomCanonicalAlias(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.canonical_alias`` event.
    """

    #: The canonical alias for this room.
    alias: Optional[str] = attr.ib(kw_only=True)

    #: The list of alternative aliases for this room.
    alt_aliases: List[str] = attr.ib(factory=list, kw_only=True)


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
    join_rule: MatrixRoomJoinRule = attr.ib(converter=MatrixRoomJoinRule, kw_only=True)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomName(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.name`` event.
    """

    #: The name of this room.
    name: str = attr.ib(kw_only=True)


@attr.s(frozen=True, slots=True)
class MatrixEventRoomTopic(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.topic`` event.
    """

    #: The room's topic text.
    topic: str = attr.ib(kw_only=True)


class HistoryVisibility(enum.Enum):
    """
    Enumeration of valid history visiblity values.
    """

    #: History is readable by anyone, on any server, no matter what.
    WORLD_READABLE = "world_readable"

    #: History is readable by all current members.
    SHARED = "shared"

    #: History is readable from the point a member is invited onwards, but not before. Events stop
    #: being accessible when a member is neither joined nor invited.
    INVITED = "invited"

    #: History is accessible to newly joined members from the point that they joined. Events before
    #: that point are not accessible, and events after a member is no longer joined are not
    #: accessible.
    JOINED = "joined"


@attr.s(frozen=True, slots=True)
class MatrixEventRoomHistoryVisibility(MatrixHttpEventContent):
    """
    Wrapper for content of the ``m.room.history_visibility`` event.
    """

    #: The visibility of historical events in this room.
    visibility: HistoryVisibility = attr.ib(kw_only=True, converter=HistoryVisibility)
