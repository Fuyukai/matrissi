from __future__ import annotations

import abc
import copy
from collections import defaultdict
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    Iterator,
    Optional,
    Type,
    TypeVar,
    Union,
)

from matriisi.dataclasses.member import RoomMember
from matriisi.http.httpevents import (
    MatrixEventRoomCreate,
    MatrixEventRoomMember,
    MatrixHttpEventContent,
    MatrixRoomBaseStateEvent,
    MatrixRoomMemberMembership,
    MatrixRoomStateEvent,
)
from matriisi.identifier import Identifier

T = TypeVar("T", bound=MatrixHttpEventContent)

if TYPE_CHECKING:
    from matriisi.identifier import IDENTIFIER_TYPE
    from matriisi.robotics.roboclient import RoboClient


class Room(abc.ABC):
    """
    A room is the most fundamental unit of Matrix communication. All events are sent through rooms,
    and all events are received through rooms.

    A room must not be created outside of internal Matriisi code.
    """

    def __init__(
        self,
        client: RoboClient,
        identifier: Identifier,
    ):
        """
        :param client: The :class:`.RoboClient` this room was received on.
        :param identifier: The :class:`.Identifier` for this room.
        """

        #: The roboclient for this room.
        self.client = client

        #: The internal :class:`.Identifier` for this room (non-human friendly).
        self.id = identifier

        self._state_events: Dict[str, Dict[str, MatrixRoomBaseStateEvent]] = defaultdict(lambda: {})

        # used internally for replaying events
        self._last_known_event_id: str = ""

    def __str__(self):
        return f"<{type(self).__name__} id='{self.id}'>"

    @property
    def last_known_event_id(self) -> str:
        """
        :return: The last known event ID received. This is primarily for internal usage when
                 replaying history.
        """
        return self._last_known_event_id

    ## Event Helpers ##

    def find_event(
        self,
        event_type: str,
        state_key: str,
        content_type: Type[T] = None,
    ) -> Optional[MatrixRoomBaseStateEvent[T]]:
        """
        Finds an event in the state events, using the ``event_type`` and ``state_key``.
        """
        subdict = self._state_events[event_type]
        if state_key is not None:
            evt = subdict.get(state_key)
            if not evt:
                return None

            return evt

        # no state key, search by type
        for event in subdict.values():
            if isinstance(event.content, content_type):
                return event

        return None

    def find_all_events(
        self,
        event_type: str,
        state_key: str = None,
        content_type: Type[T] = None,
    ) -> Iterable[Union[MatrixRoomBaseStateEvent[T]]]:
        """
        Find all events matching the criteria.

        :param event_type: The ``type`` field of the events to find.
        :param state_key: The ``state_key`` field of the events to find.
        :param content_type: The type of the body for this event. Optional, for typing.
        :return:
        """
        subdict = self._state_events[event_type]
        for k, v in subdict.items():
            if state_key is None:
                yield v
            elif k == state_key:
                yield v
            elif isinstance(v, content_type):
                yield v

    def _update_state(self, event: MatrixRoomBaseStateEvent):
        """
        Updates the room state.
        """
        # this should never happen
        try:
            self._last_known_event_id = event.event_id
        except AttributeError:
            # stripped state...
            pass

        # skip state events
        if not hasattr(event, "state_key"):
            return

        subdict = self._state_events[event.type]
        subdict[event.state_key] = event  # type: ignore

    def _snapshot(self) -> Room:
        """
        Takes a snapshot of this room at its current state.
        """

        r = type(self)(self.client, self.id)
        d = {}
        for typ, subdict in self._state_events.items():
            d[typ] = subdict.copy()

        r._state_events = d
        return r

    def member(self, id: IDENTIFIER_TYPE) -> Optional[RoomMember]:
        """
        Gets a member from this room.

        :param id: The identifier of the member.
        :return: The member object, or None if there is no such member.
        """
        event = self.find_event("m.room.member", str(id), MatrixEventRoomMember)
        if event is None:
            return None

        return RoomMember(event, self)

    # these are cached as these never change (m.room.create is immutable)
    @cached_property
    def creator_id(self) -> Identifier:
        """
        :return: The :class:`.Identifier` of the user that created this room.
        """
        evt = self.find_event("m.room.create", "", MatrixEventRoomCreate)
        assert evt, "room is missing m.room.create state"

        return evt.content.creator

    @cached_property
    def federated(self) -> bool:
        """
        :return: If this room is federated.
        """
        evt = self.find_event("m.room.create", "", MatrixEventRoomCreate)
        assert evt, "room is missing m.room.create state"

        return evt.content.m_federate

    # not cached properties
    def creator(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` for the creator of this room.
        """
        event = self.find_event("m.room.create", "", MatrixEventRoomCreate)
        assert event, "room is missing m.room.create event?"

        uid = event.content.creator
        member = self.member(uid)
        assert member, f"room is missing creator member {uid} event?"

        return member


class JoinedRoom(Room):
    """
    A room that has been joined.
    """

    @property
    def joined_members(self) -> Iterator[RoomMember]:
        """
        :return: An iterator for the joined members in this room.
        """

        for event in self._state_events[
            "m.room.member"
        ].values():  # type: MatrixRoomBaseStateEvent[MatrixEventRoomMember]
            if event.content.membership != MatrixRoomMemberMembership.JOIN:
                continue

            yield RoomMember(event, self)

    async def send_event(self, event_type: str, data, *, txnid: str = None, state_key: str = None):
        """
        Low-level helper to directly send any event to this room.
        """

        await self.client.http_client.send_event(
            self.id,
            event_type=event_type,
            txnid=txnid,
            state_key=state_key,
            body=data,
        )

    ## High-level helpers ##
    async def send_text_message(self, message_content: str, **extra):
        """
        Sends a text message to this room.

        :param message_content: The content of the message.
        :param extra: Any extra data.
        :return: Nothing.
        """

        body = {"msgtype": "m.text", "body": message_content, **extra}

        return await self.send_event(event_type="m.room.message", data=body)


class InvitedRoom(Room):
    """
    A room that you have been invited to.
    """

    @cached_property
    def inviter_id(self) -> Identifier:
        """
        :return: The identifier of the member that invited you to this room.
        """
        event = self.find_event("m.room.member", str(self._client.uid), MatrixEventRoomMember)
        assert event, "room is missing member event for ourself?"

        return event.sender
