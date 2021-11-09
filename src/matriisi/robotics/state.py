from __future__ import annotations

import logging
from collections import deque
from functools import partial
from io import StringIO
from typing import TYPE_CHECKING, Deque, List, Optional, cast

import attr
from prettyprinter import pprint
from trio import MemorySendChannel

from matriisi.dataclasses.message import Message
from matriisi.dataclasses.room import Room
from matriisi.http import (
    MatrixEventRoomMember,
    MatrixEventRoomMessage,
    MatrixJoinedRoom,
    MatrixRoomBaseEvent,
    MatrixRoomBaseStateEvent,
    MatrixRoomEvent,
    MatrixRoomMemberMembership,
    MatrixSync, MatrixHttpEvent,
)
from matriisi.id_dict import IdentifierDict
from matriisi.identifier import Identifier
from matriisi.robotics.event import (
    Event,
    MessageEvent,
    MessageReplyEvent,
)
from matriisi.robotics.event.room import (
    RoomMemberBannedEvent,
    RoomMemberInviteRejectedEvent,
    RoomMemberInviteRevokedEvent,
    RoomMemberJoinedEvent,
    RoomMemberKickedEvent,
    RoomMemberLeftEvent,
    RoomMemberUnbannedEvent, RoomMemberInvitedEvent, RoomMeJoinedEvent,
)

if TYPE_CHECKING:
    from matriisi.robotics.roboclient import RoboClient

logger = logging.getLogger(__name__)

_INVITE = MatrixRoomMemberMembership.INVITE
_JOIN = MatrixRoomMemberMembership.JOIN
_LEAVE = MatrixRoomMemberMembership.LEAVE
_BAN = MatrixRoomMemberMembership.BAN
_KNOCK = MatrixRoomMemberMembership.KNOCK


def stringify_event(evt: MatrixHttpEvent):
    stream = StringIO()
    pprint(evt, stream=stream)
    return stream.getvalue()


@attr.s()
class MatrixState(object):
    """
    Encapsulates the global state for the current roboclient, as well as handles generating events.
    """

    # TODO: Account data
    #: The roboclient using this state.
    roboclient: RoboClient = attr.ib()

    #: The channel to dispatch events over.
    event_channel: MemorySendChannel[Event] = attr.ib()

    #: A deque of cached events.
    cached_events: Deque[MatrixRoomEvent] = attr.ib(factory=partial(deque, maxlen=1000))

    #: The mapping of rooms data.
    rooms: IdentifierDict[Room] = attr.ib(factory=IdentifierDict)

    #: The ``next_batch`` key.
    next_batch: Optional[str] = attr.ib(default=None)

    @staticmethod
    def _handle_m_room_message(
        before: Room, snapshot: Room, event: MatrixRoomEvent[MatrixEventRoomMessage]
    ):
        """
        Handles a new room message.
        """

        message = Message(event=event, room=snapshot)

        reply = event.content.relates_to.replying_to
        if reply is not None:
            return MessageReplyEvent(snapshot, message)

        return MessageEvent(snapshot, message)

    @staticmethod
    def _handle_m_room_member(
        before: Room, snapshot: Room, event: MatrixRoomBaseStateEvent[MatrixEventRoomMember]
    ):
        """
        Handles a member event.
        """

        # this requires a whole bunch of heuristics to detect what actually changed
        previous_event = before.find_event(
            "m.room.member", event.state_key, MatrixEventRoomMember
        )
        if previous_event is None:
            pm = _LEAVE
        else:
            pm = previous_event.content.membership

        nm = event.content.membership

        # check membership changes
        if pm != nm:
            # oh boy...

            if pm == _INVITE and nm == _JOIN:  # accepted invite
                return RoomMemberJoinedEvent(snapshot, event.sender, was_invited=True)

            elif pm == _INVITE and nm == _LEAVE:  # rejected/revoked invite
                rejected_id = Identifier.parse(event.state_key)
                if event.sender == rejected_id:
                    return RoomMemberInviteRejectedEvent(snapshot, event.sender)
                else:
                    return RoomMemberInviteRevokedEvent(snapshot, rejected_id, event.sender)

            elif pm == _JOIN and nm == _LEAVE:  # left room somehow
                member_id = Identifier.parse(event.state_key)
                if event.sender == member_id:
                    return RoomMemberLeftEvent(snapshot, member_id)
                else:
                    return RoomMemberKickedEvent(
                        snapshot, kicked_id=member_id, kicker_id=event.sender
                    )

            elif pm == _LEAVE and nm == _INVITE:  # newly invited
                member_id = Identifier.parse(event.state_key)
                return RoomMemberInvitedEvent(snapshot, invitee_id=member_id, inviter_id=event.sender)

            elif pm == _LEAVE and nm == _JOIN:  # newly joined
                member_id = Identifier.parse(event.state_key)
                return RoomMemberJoinedEvent(snapshot, member_id, was_invited=False)

            elif pm == _BAN and nm == _LEAVE:  # unbanned
                member_id = Identifier.parse(event.state_key)
                return RoomMemberUnbannedEvent(
                    snapshot, unbanned_id=member_id, unbanner_id=event.sender
                )

            elif nm == _BAN:  # banned, in some form
                banner = event.sender
                banee = Identifier.parse(event.state_key)
                return RoomMemberBannedEvent(
                    snapshot, banned_id=banee, banner_id=banner, was_in_room=pm == _JOIN
                )

            else:
                before = stringify_event(previous_event)
                after = stringify_event(event)
                logger.warning(
                    f"Invalid or unsupported membership transistion detected: {pm} -> {nm}\n\n"
                    f"previous event: {before}\n"
                    f"next event: {after}"
                )

        else:
            if pm == _JOIN and nm == _JOIN:
                raise NotImplementedError()

        before = stringify_event(previous_event)
        after = stringify_event(event)
        logger.warning(
            "all heuristics failed when parsing member event. this is definitely a bug!\n\n"
            f"previous event: {before}\n"
            f"next event: {after}"
        )

    async def _backfill_events(self, room_id: Identifier, prev_batch: str, last_known_id: str):
        """
        Backfills events from Matrix.

        :param room_id: The room ID to backfill for.
        :param prev_batch: The token to use to get the previous set of events.
        :param last_known_id: The last known event ID.
        """

        logger.debug(f"Rewinding until we see {last_known_id}.")

        evts = deque()
        token = prev_batch
        while True:
            logger.debug(f"Rewinding from {token}")
            events = await self.roboclient.http_client.get_events(
                room_id=room_id, from_token=token, reverse=True, limit=50
            )
            for event in events.chunk:
                # check if we already saw this one, if so it's definitely the last one
                if event.event_id == last_known_id:
                    logger.debug(
                        f"Rewinded successfully to {event.event_id}, got {len(evts)} " f"events"
                    )
                    return evts
                else:
                    # events are returned in reverse order, so we need to append in reverse order
                    evts.appendleft(event)

            if events.end is None:
                logger.warning(
                    "Reached end of timeline when backfilling events, this should not " "happen"
                )
            else:
                token = events.end

    async def _process_joined_room(
        self, room_data: MatrixJoinedRoom, *, dont_backfill: bool
    ) -> List[Event]:
        """
        Processes a single joined room.
        """

        events = []

        matrix_events: List[MatrixRoomBaseEvent] = []
        matrix_events += room_data.state
        matrix_events += room_data.timeline.events

        last_room = self.rooms.get(room_data.room_id)

        if last_room is not None:
            room = last_room
            # room already existed, definitely not the first sync
            # check if we need to backfill data (the timeline is limited)
            if not dont_backfill and room_data.timeline.limited:
                logger.warning("Server dropped events, rewinding event stream")

                # okay, backfill events until we reach the last known event ID.
                evts = await self._backfill_events(
                    room_data.room_id,
                    room_data.timeline.prev_batch,
                    last_room.last_known_event_id,
                )
                matrix_events = list(evts) + matrix_events
        else:
            # new room, start with a joined room event
            room = Room(self.roboclient, room_data.room_id)
            self.rooms[room_data.room_id] = room
            events.append(RoomMeJoinedEvent(room))

        # replay events onto the room
        for evt in matrix_events:
            self.cached_events.append(evt)  # type: ignore

            before = room.snapshot()
            if isinstance(evt, MatrixRoomBaseStateEvent):
                # noinspection PyProtectedMember
                room._update_state(evt)

            if last_room is not None:
                evt_type = evt.type.replace(".", "_")
                event_handler = getattr(self, f"_handle_{evt_type}", None)

                if event_handler:
                    snapshot = room.snapshot()
                    result = event_handler(before, snapshot, evt)

                    if result is not None:
                        events.append(result)

        return events

    async def sync(self, sync: MatrixSync, *, initial_batch: bool):
        """
        Synchronises local state with the server state.

        :param sync: The :class:`.MatrixSync` returned from the server.
        :param initial_batch: If this is the first sync. No events will be fired if it is.
        """
        self.next_batch = sync.next_batch

        events = []

        for id, room_data in sync.room_data.joined.items():
            events += await self._process_joined_room(room_data, dont_backfill=initial_batch)

        # drop the events on the floor
        if initial_batch:
            return

        for evt in events:
            await self.event_channel.send(evt)
