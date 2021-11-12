from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import List, Mapping, Optional

import attr

__all__ = (
    "MatrixPresence",
    "MatrixVersions",
    "MatrixWhoami",
    "MatrixSync",
    "MatrixSyncRooms",
    "MatrixJoinedRoom",
    "MatrixKnockRoom",
    "MatrixTimeline",
    "MatrixInvitedRoom",
    "MatrixLeftRoom",
    "MatrixRoomSummary",
    "MatrixRoomMessages",
    "MatrixCapabilities",
)

from matriisi.http.httpevents import (
    MatrixHttpEvent,
    MatrixRoomBaseStateEvent,
    MatrixRoomEvent,
    MatrixRoomStateEvent,
)
from matriisi.id_dict import IdentifierDict
from matriisi.identifier import Identifier


class MatrixPresence(enum.Enum):
    """
    Enumeration of possible presence values.
    """

    UNKNOWN = 0
    OFFLINE = 1
    ONLINE = 2
    UNAVAILABLE = 3


@attr.s(frozen=True, slots=True)
class MatrixVersions(object):
    """
    Structure representing the protocol versions a matrix server supports.
    """

    #: The protocol versions the server supports.
    versions: List[str] = attr.ib()

    #: The unstable features the server supports.
    unstable_features: Mapping[str, bool] = attr.ib(factory=dict)

    def supports(self, feature: str) -> bool:
        """
        Checks if the server supports the specified unstable ``feature``.
        """
        return self.unstable_features.get(feature, False)


@attr.s(frozen=True, slots=True)
class MatrixWhoami(object):
    """
    Structure for the /whoami endpoint.
    """

    #: The user ID for this client.
    user_id: Identifier = attr.ib(converter=Identifier.parse)

    #: The device ID for this client.
    device_id: str = attr.ib()


@attr.s(frozen=True, slots=True)
class MatrixRoom(object):
    """
    Base class for all matrix rooms.
    """

    #: The ID for this room.
    room_id: Identifier = attr.ib(converter=Identifier.parse)


@attr.s(frozen=True, slots=True)
class MatrixInvitedRoom(MatrixRoom):
    """
    Structure for an invite room. This strips out the ``invite_state`` object (at least for now)
    and jumps straight to ``events``.
    """

    #: The list of stripped state events for this room.
    invite_state: List[MatrixRoomBaseStateEvent] = attr.ib(factory=list)


@attr.s(frozen=True, slots=True)
class MatrixKnockRoom(MatrixRoom):
    """
    Structure for a knocked room. This strips out the ``knock_state`` object (at least for now)
    and jumps straight to ``events``.
    """

    #: The list of stripped state events for this room.
    knock_state: List[MatrixRoomBaseStateEvent] = attr.ib(factory=list)


@attr.s(frozen=True, slots=True)
class MatrixTimeline(Iterable[MatrixRoomEvent]):
    """
    A timeline of events.
    """

    #: The events that have happened since the last sync.
    events: List[MatrixRoomEvent] = attr.ib()

    #: If this is a limited view.
    limited: bool = attr.ib(default=False)

    #: The previous batch token.
    prev_batch: Optional[str] = attr.ib(default=None)

    def __iter__(self):
        return iter(self.events)


@attr.s(frozen=True, slots=True)
class RoomWithTimeline(MatrixRoom):
    """
    Mixin class for join/left rooms that have account_data, state, and timeline data.
    """

    #: The private account data for this room.
    account_data: List[MatrixHttpEvent] = attr.ib()

    #: The updated state between ``since``, and the start of the timeline.
    state: List[MatrixRoomBaseStateEvent] = attr.ib()

    #: The timeline of events between ``since`` and now.
    timeline: MatrixTimeline = attr.ib()


@attr.s(frozen=True, slots=True)
class MatrixLeftRoom(RoomWithTimeline):  # same fields as RoomWithTimeline.
    """
    Structure for a room that has been left.
    """


@attr.s(frozen=True, slots=True)
class MatrixRoomSummary:
    """
    The summary info of this room.
    """

    #: The users used to generate a room name.
    heroes: List[str] = attr.ib(factory=list)

    #: The number of members with a membership of ``invite``.
    invited_member_count: Optional[int] = attr.ib(default=None)

    #: The number of members with a membership of ``joined``.
    joined_member_count: Optional[int] = attr.ib(default=None)


@attr.s(frozen=True, slots=True)
class MatrixJoinedRoom(RoomWithTimeline):
    """
    Structure for a room that has been joined (i.e. a room the user is currently in).
    """

    #: The list of emphemeral events.
    ephemeral: List[MatrixHttpEvent] = attr.ib()

    #: The summary for this room.
    summary: Optional[MatrixRoomSummary] = attr.ib(default=None)


@attr.s(frozen=True, slots=True)
class MatrixSyncRooms(object):
    """
    Structure for the rooms part of the sync endpoint.
    """

    #: The rooms that the current user has been invited to.
    invite: IdentifierDict[MatrixInvitedRoom] = attr.ib()

    #: The rooms that the current user has joined.
    joined: IdentifierDict[MatrixJoinedRoom] = attr.ib()

    #: The rooms that the current user has left.
    leave: IdentifierDict[MatrixLeftRoom] = attr.ib()

    # TODO: ``knock``.


@attr.s(frozen=True, slots=True)
class MatrixSync(object):
    """
    Data class for the data returned by the ``/sync`` endpoint.
    """

    #: The ``next_batch`` token.
    next_batch: str = attr.ib()

    #: The list of state events stored under account data.
    account_data: List[MatrixHttpEvent] = attr.ib()

    #: The room data for this sync.
    room_data: MatrixSyncRooms = attr.ib()


@attr.s(frozen=True, slots=True)
class MatrixRoomMessages(object):
    """
    Data class for the data returned by the ``/{roomId}/messages`` endpoint.
    """

    #: The chunk of events for this response.
    chunk: List[MatrixRoomEvent] = attr.ib()

    #: The token corresponding to the start of ``chunk``. This is the same as ``from``.
    start: str = attr.ib()

    #: The token corresponding to the end of ``chunk``. This may be absent if the end of the
    #: timeline has been reached.
    end: Optional[str] = attr.ib(default=None)

    #: The state events for this chunk.
    state: List[MatrixRoomStateEvent] = attr.ib(factory=list)


@attr.s(frozen=True, slots=True)
class MatrixCapabilities(object):
    """
    Data class for returned capabilities.
    """

    #: The default room version, as created by the server.
    default_room_version: str = attr.ib()

    #: The available room versions.
    available_versions: Mapping[str, str] = attr.ib()

    #: If the password change capability is enabled.
    can_change_password: bool = attr.ib()

    # MSC3283 support
    # > clients should behave as if they were present and set to true.
    #: If users can change their display name.
    can_change_displayname: bool = attr.ib(default=True)

    #: If users can change their avatar.
    can_change_avatar: bool = attr.ib(default=True)

    #: If users can change their 3PIDs.
    can_change_3pids: bool = attr.ib(default=True)
