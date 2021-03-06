from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncContextManager, Optional, Type

import trio

from matriisi.dataclasses.room import Room
from matriisi.event import Event
from matriisi.event.bus import EventBus, open_event_bus
from matriisi.http import MatrixCapabilities, MatrixHttp, create_http_client
from matriisi.identifier import Identifier
from matriisi.state import MatrixState
from matriisi.utils import asynccontextmanager

if TYPE_CHECKING:
    from matriisi.identifier import IDENTIFIER_TYPE

logger = logging.getLogger(__name__)


class RoboClient(object):
    """
    A client for a Matrix bot. This implements a high-level wrapper around the Matrix HTTP API.
    """

    SUPPORTED_ROOM_VERSIONS = {"6", "7", "8", "9"}

    def __init__(self, http_client: MatrixHttp, event_bus: EventBus):
        """
        :param http_client: The configured :class:`.MatrixHttp` client that the roboclient will
                            use for connecting to your homeserver.
        :param event_bus: The :class:`.EventBus` to dispatch events on.
        """

        self.http_client = http_client
        self._event_bus = event_bus
        self._sync_filter = "{}"

        #: The shared state for this client.
        self.state = MatrixState(self, self._event_bus._write)

        # these properties are set in run() usually.
        #: The UID of this client.
        self.uid: Identifier = None  # type: ignore

        #: The capabilities of the remote home server.
        self.capabilities: MatrixCapabilities = None  # type: ignore

    async def run(self):
        """
        Runs the roboclient forever. This will synch messages from the server and dispatch them
        around.
        """
        self.capabilities = await self.http_client.capabilities()

        # we speak room versions 6 through 9
        if not any(r in self.capabilities.available_versions for r in self.SUPPORTED_ROOM_VERSIONS):
            raise ValueError(
                "Server speaks an incompatible set of room versions\n"
                f"Required: Any of {self.SUPPORTED_ROOM_VERSIONS}\n"
                f"Got: {self.capabilities.available_versions}"
            )

        whoami = await self.http_client.whoami()
        self.uid = whoami.user_id

        logger.info(f"Logged in user is {self.uid}")
        self._sync_filter = json.dumps(
            {"room": {"ephemeral": {"types": []}, "timeline": {"limit": 50}}}
        )

        last_sync = await self.http_client.sync()
        await self.state.sync(last_sync, initial_batch=True)

        # todo: send initial sync event

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self._sync_loop)
            nursery.start_soon(self._event_bus._run_loop)

    async def _sync_loop(self):
        """
        Synchronises with the server in a loop forever.
        """

        while True:
            with trio.move_on_after(31) as scope:
                logger.debug("Synchronising with the server...")
                last_sync = await self.http_client.sync(
                    since=self.state.next_batch, timeout=30 * 1000, filter=self._sync_filter
                )

            # TODO: Only do this a few times.
            if scope.cancel_called:
                logger.warning("Server sync timed out, skipping sync phase")
            else:
                await self.state.sync(last_sync, initial_batch=False)

    def event(self, type: Type[Event]):
        """
        Decorator that marks a function as an event handler.

        :param type: The type of the event.
        :return: A callable that takes a function and returns it.
        """

        def inner(fn):
            fn.__evttype__ = type
            self._event_bus.register(type, fn)

            return fn

        return inner

    def all_events(self, fn: Any) -> Any:
        """
        Decorator that marks a function as handlinng all events.

        :param fn: The function for the event.
        :return: The same function.
        """

        self._event_bus.register_any_handler(fn)

    ## Global Functions ##

    def get_room(self, room_id: IDENTIFIER_TYPE) -> Optional[Room]:
        """
        Gets a room.

        :param room_id: The identifier for the room.
        :return: A snapshot of the room, if it exists.
        """

        room = self.state.rooms.get(room_id)
        if room:
            return room.snapshot()

    def find_room(self, room_id: IDENTIFIER_TYPE) -> Optional[Room]:
        """
        Finds a room, either by its identifier or its name.

        .. warning::

            Room names are not unique.

        :param room_id: The identifier or name of the room.
        :return: A snapshot of the room, if it exists.
        """

        room = self.get_room(room_id)
        if room:
            return room

        for room in self.state.rooms.values():
            if room.name == room_id:
                return room.snapshot()


@asynccontextmanager
async def create_robo_client(
    homeserver: str,
    *,
    access_token: str = None,
) -> AsyncContextManager[RoboClient]:
    """
    Creates a new :class:`.RoboClient`.

    :param homeserver: The homeserver to connect to. This should be the domain part of your bot's
                       user identifier.
    :param access_token: The access token to use for this bot.
    """
    async with create_http_client(
        homeserver_hostname=homeserver
    ) as client, open_event_bus() as bus:
        client.set_auth_token(access_token)
        roboclient = RoboClient(client, bus)
        yield roboclient
