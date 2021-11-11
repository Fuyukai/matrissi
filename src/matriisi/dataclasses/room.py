from __future__ import annotations

from collections import defaultdict
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    Iterator,
    Optional,
    Type,
    TypeVar,
    Union,
)

import markdown2
from trio.lowlevel import checkpoint

from matriisi.dataclasses.member import RoomMember
from matriisi.dataclasses.message import Message
from matriisi.http.httpevents import (
    CONTENT_TYPE,
    MatrixEventRoomCreate,
    MatrixEventRoomMember,
    MatrixEventRoomMessage,
    MatrixEventRoomName,
    MatrixEventRoomTopic,
    MatrixHttpEventContent,
    MatrixRoomBaseStateEvent,
    MatrixRoomEvent,
    MatrixRoomMemberMembership,
    MatrixRoomStateEvent,
)
from matriisi.identifier import Identifier

T = TypeVar("T", bound=MatrixHttpEventContent)

if TYPE_CHECKING:
    from matriisi.identifier import IDENTIFIER_TYPE
    from matriisi.roboclient import RoboClient


# {
#     "content": {
#         "body": "* **four**",
#         "format": "org.matrix.custom.html",
#         "formatted_body": "* <strong>four</strong>",
#         "im.nheko.relations.v1.relations": [
#             {
#                 "event_id": "$Sm1M2dmwDZ5_yl179mEZmm7ovI72EbCJoEJDjtZmGdI",
#                 "rel_type": "m.replace"
#             }
#         ],
#         "m.new_content": {
#             "body": "**four**",
#             "format": "org.matrix.custom.html",
#             "formatted_body": "<strong>four</strong>",
#             "msgtype": "m.text"
#         },
#         "m.relates_to": {
#             "event_id": "$Sm1M2dmwDZ5_yl179mEZmm7ovI72EbCJoEJDjtZmGdI",
#             "rel_type": "m.replace"
#         },
#         "msgtype": "m.text"
#     },
#     "event_id": "$FPuoE-AKvZDILyIJ9BqhCZbA8HshvpmeBAS3KTnPM0A",
#     "origin_server_ts": 1636571392025,
#     "sender": "@lura:veriny.tf",
#     "type": "m.room.message",
#     "unsigned": {
#         "age": 130,
#         "transaction_id": "mWZf8EZEVHbkyFDfKt51rufZ2EpGzg9Aa"
#     }
# }


class Room(object):
    """
    A room is the most fundamental unit of Matrix communication. All events are sent through rooms,
    and all events are received through rooms.

    Only joined rooms are represented via this class; invited/knocked/left rooms are represented
    separately.

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

        self._state_events: Dict[str, Dict[str, MatrixRoomStateEvent]] = defaultdict(lambda: {})

        # used internally for replaying events
        self._last_known_event_id: str = ""

    def __str__(self):
        s = f"<{type(self).__name__} id='{self.id}'"
        name = self.name
        if name is not None:
            s += f" name='{self.name}'>"
        else:
            s += ">"

        return s

    __repr__ = __str__

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
    ) -> Iterable[Union[MatrixRoomStateEvent[T]]]:
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

    def _update_state(self, event: MatrixRoomStateEvent[Any]):
        """
        Updates the room state.
        """
        # this should never happen
        self._last_known_event_id = event.event_id

        # skip state events
        if not hasattr(event, "state_key"):
            return

        subdict = self._state_events[event.type]
        # room membership removal is handled specially
        if event.type == "m.room.member":
            # remove old member events that are left. invites, bans, etc are cached
            if event.content.membership == MatrixRoomMemberMembership.LEAVE:
                subdict.pop(event.state_key, None)
                return

        subdict[event.state_key] = event  # type: ignore

    def snapshot(self) -> Room:
        """
        Takes a snapshot of this room at its current state.
        """

        r = type(self)(self.client, self.id)
        d = r._state_events
        for typ, subdict in self._state_events.items():
            d[typ] = subdict.copy()

        return r

    def member(self, id: IDENTIFIER_TYPE) -> Optional[RoomMember]:
        """
        Gets a member from this room.

        :param id: The identifier of the member.
        :return: The member object, or None if there is no such member with the JOIN membership.
        """

        event = self.find_event("m.room.member", str(id), MatrixEventRoomMember)
        if event is None:
            return None

        # ban/invite members are returned separately
        if event.content.membership != MatrixRoomMemberMembership.JOIN:
            return None

        return RoomMember(event, self)

    @property
    def members(self) -> Iterator[RoomMember]:
        """
        :return: A generator for the joined members of this room.
        """

        for state_key, event in self._state_events["m.room.member"].items():
            content: MatrixEventRoomMember = event.content
            if content.membership != MatrixRoomMemberMembership.JOIN:
                continue

            yield RoomMember(event, self)

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

    @property
    def name(self) -> Optional[str]:
        """
        Returns the name for this room.
        """

        evt = self.find_event("m.room.name", "", MatrixEventRoomName)
        if evt is None:
            return None

        name = evt.content.name
        if not name:
            return None

        return name

    @property
    def topic(self) -> Optional[str]:
        """
        Returns the topic for this room.
        """

        evt = self.find_event("m.room.topic", "", MatrixEventRoomTopic)
        if evt is None:
            return None

        topic = evt.content.topic
        if not topic:
            return None

        return topic

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

    async def send_event(
        self,
        event_type: str,
        data,
        *,
        txnid: str = None,
        state_key: str = None,
        wait_for_sync: bool = False,
        returned_event_type: Type[CONTENT_TYPE] = None,
    ) -> Union[str, MatrixRoomEvent[CONTENT_TYPE]]:
        """
        Low-level helper to directly send any event to this room.

        :param event_type: The type of event to send.
        :param data: The body of the event.
        :param txnid: The transaction ID. If unset, will be generated.
        :param state_key: The state key for a state event. If set, this will be a state event,
                          otherwise it will be a regular timeline event.
        :param wait_for_sync: If True, waits for the next sync() to retrieve the full event returned
                              from the server. Otherwise, simply returns the event ID.
        :return: The event/event ID as generated by the homeserver.
        """

        result = await self.client.http_client.send_event(
            self.id,
            event_type=event_type,
            txnid=txnid,
            state_key=state_key,
            body=data,
        )

        if wait_for_sync:
            while True:
                event = self.client.state.find_event(result)
                if event is not None:
                    await checkpoint()
                    return event
                else:
                    await self.client.state.wait_until_sync()
        else:
            return result

    ## High-level helpers ##
    async def send_text_message(
        self,
        message_content: str,
        *,
        render_markdown: bool = True,
        use_notice: bool = True,
        wait_for_sync: bool = False,
        **extra,
    ) -> Union[str, Message]:
        """
        Sends a text message to this room.

        :param message_content: The content of the message.
        :param render_markdown: If True, then ``message_content`` will be turned into HTML from
                                Markdown.
        :param use_notice: If True, then this will be an ``m.notice`` message (recommended).
        :param wait_for_sync: If True, waits for the next sync() to retrieve the full event returned
                              from the server. Otherwise, simply returns the event ID.
        :param extra: Any extra data to send in the event content.
        :return: The event ID or :class:`.Message`.
        """

        if use_notice:
            type = "m.notice"
        else:
            type = "m.text"

        body = {"msgtype": type, "body": message_content, **extra}

        if render_markdown:
            html_body = markdown2.markdown(
                message_content,
                extras=["fenced-code-blocks", "strike", "tables", "break-on-newline"],
            )
            body["format"] = "org.matrix.custom.html"
            body["formatted_body"] = html_body

        evt = await self.send_event(
            event_type="m.room.message",
            data=body,
            wait_for_sync=wait_for_sync,
            returned_event_type=MatrixEventRoomMessage,
        )

        if wait_for_sync:
            return Message(evt, self)
        else:
            return evt

    async def edit_text_message(
        self,
        event_id: str,
        message_content: str,
        *,
        render_markdown: bool = True,
        use_notice: bool = True,
        wait_for_sync: bool = False,
        **extra,
    ):
        """
        Edits a textual message.

        :param event_id: The event ID of the message to edit.
        :param message_content: The content of the message to replace.
        :param render_markdown: If True, then ``message_content`` will be turned into HTML from
                                Markdown.
        :param use_notice: If True, then this will be an ``m.notice`` message (recommended).
        :param wait_for_sync: If True, waits for the next sync() to retrieve the full event returned
                              from the server. Otherwise, simply returns the event ID.
        :param extra: Any extra data to send in the event content.
        """

        if use_notice:
            type = "m.notice"
        else:
            type = "m.text"

        body = {
            "body": f"* {message_content}",  # seems to be the standard edit format
            "msgtype": type,
            "m.new_content": {
                "body": message_content,
                "msgtype": type,
            },
            "im.nheko.relations.v1.relations": [
                {
                    "event_id": event_id,
                    "rel_type": "m.replace",
                }
            ],
            "m.relates_to": {
                "event_id": event_id,
                "rel_type": "m.replace",
            },
            **extra,
        }

        if render_markdown:
            html_body = markdown2.markdown(
                message_content,
                extras=["fenced-code-blocks", "strike", "tables", "break-on-newline"],
            )

            for sd in (body, body["m.new_content"]):
                sd["format"] = "org.matrix.custom.html"
                sd["formatted_body"] = html_body

        evt = await self.send_event(
            event_type="m.room.message",
            data=body,
            wait_for_sync=wait_for_sync,
            returned_event_type=MatrixEventRoomMessage,
        )

        if wait_for_sync:
            return Message(evt, self)
        else:
            return evt
