from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, List, Optional

import attr
from trio import MemorySendChannel

from matriisi.dataclasses.message import Message
from matriisi.dataclasses.room import JoinedRoom
from matriisi.http import (
    MatrixEventRoomMessage,
    MatrixJoinedRoom,
    MatrixRoomBaseEvent,
    MatrixRoomBaseStateEvent,
    MatrixRoomEvent,
    MatrixSync,
)
from matriisi.id_dict import IdentifierDict
from matriisi.identifier import Identifier
from matriisi.robotics.event import Event, MessageEvent, RoomJoinedEvent

if TYPE_CHECKING:
    from matriisi.robotics.roboclient import RoboClient

logger = logging.getLogger(__name__)


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

    #: The mapping of rooms data.
    rooms: IdentifierDict[JoinedRoom] = attr.ib(factory=IdentifierDict)

    #: The ``next_batch`` key.
    next_batch: Optional[str] = attr.ib(default=None)

    def _handle_m_room_message(
        self, snapshot: JoinedRoom, event: MatrixRoomEvent[MatrixEventRoomMessage]
    ):
        """
        Handles a new room message.
        """

        message = Message(event=event, client=self.roboclient, room=snapshot)
        return MessageEvent(snapshot, message)

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
            room = JoinedRoom(self.roboclient, room_data.room_id)
            self.rooms[room_data.room_id] = room
            events.append(RoomJoinedEvent(room))

        # replay events onto the room
        for evt in matrix_events:
            if isinstance(evt, MatrixRoomBaseStateEvent):
                # noinspection PyProtectedMember
                room._update_state(evt)

            if last_room is not None:
                evt_type = evt.type.replace(".", "_")
                event_handler = getattr(self, f"_handle_{evt_type}", None)

                if event_handler:
                    # noinspection PyProtectedMember
                    snapshot = room._snapshot()
                    events.append(event_handler(snapshot, evt))

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
