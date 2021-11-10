from __future__ import annotations

import logging
from collections import defaultdict
from functools import partial
from typing import Any, AsyncContextManager, Awaitable, Callable, Optional, Type

import trio

from matriisi.event.base import Event
from matriisi.utils import LimitingNursery, asynccontextmanager, open_limiting_nursery

logger = logging.getLogger(__name__)


class EventBus(object):
    """
    A trionic event bus class. This class allows a tradeoff between SC and not blocking forever in
    event handlers.
    """

    def __init__(self, nursery: LimitingNursery):
        self._nursery = nursery

        self._write, self._read = trio.open_memory_channel(max_buffer_size=0)

        # list of event handlers called on *any* event
        self._any_event_handlers = []

        # mapping of type(event) -> callback
        self._event_handlers = defaultdict(list)

    @staticmethod
    async def _run_event_safely(event, cb):
        """
        Runs an event safely.
        """

        try:
            await cb(event)
        except:
            logger.exception(f"Event handler {cb} failed with exception!")

    async def _run_loop(self):
        """
        Run loop function responsible for receiving new events.
        """

        while True:
            event = await self._read.receive()
            logger.debug(f"Dispatching event {type(event)}")

            # drop insignificant events if there's no available slots
            if event.insignificant and self._nursery.available_tasks <= 0:
                logger.debug(f"Dropping insignificant event {event}")
                continue

            for handler in self._any_event_handlers:
                p = partial(self._run_event_safely, event, handler)
                await self._nursery.start(p)

            for handler in self._event_handlers[type(event)]:
                p = partial(self._run_event_safely, event, handler)
                await self._nursery.start(p)

    def register(self, type: Type[Event], fn: Callable[[Event], Awaitable[Optional[Any]]]):
        """
        Registers an event handler function.

        :param type: The type of the event to handle.
        :param fn: The function to callback with.
        """

        self._event_handlers[type].append(fn)

    def register_any_handler(self, fn: Callable[[Event], Awaitable[Optional[Any]]]):
        """
        Registers a handler for ALL events.

        :param fn: The function to call back with.
        """

        logger.warning(f"Registering event hook {fn.__qualname__}")
        self._any_event_handlers.append(fn)


@asynccontextmanager
async def open_event_bus(max_events: int = 64) -> AsyncContextManager[EventBus]:
    """
    Opens a new event bus.

    :param max_events: The maximum number of events that can be running at any given time.
    """

    async with open_limiting_nursery(max_tasks=max_events) as n:
        yield EventBus(nursery=n)
