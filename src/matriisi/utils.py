import trio
from trio import CapacityLimiter, Nursery

try:
    from contextlib import asynccontextmanager
except ImportError:
    from async_generator import asynccontextmanager


class LimitingNursery(object):
    """
    A nursery that only allows a certain amount of tasks to be ran at any one time.
    """

    def __init__(self, real_nursery: Nursery, limiter: CapacityLimiter):
        self._nursery = real_nursery
        self._limiter = limiter

    async def start(self, fn):
        """
        Starts a new task. This will block until the capacity limiter has a token available.
        """

        async def inner(task_status):
            async with self._limiter:
                task_status.started()
                await fn()

        await self._nursery.start(inner)

    @property
    def available_tasks(self):
        return self._limiter.available_tokens


@asynccontextmanager
async def open_limiting_nursery(max_tasks: int = 64):
    """
    Opens a capacity limiting nursery.

    :param max_tasks: The maximum number of tasks that can run simultaneously.
    """
    async with trio.open_nursery() as n:
        yield LimitingNursery(n, CapacityLimiter(max_tasks))
