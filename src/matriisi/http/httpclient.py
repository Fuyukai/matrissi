"""
Matrix HTTP client code.
"""
from __future__ import annotations

import enum
import inspect
import logging
import secrets
import sys
from importlib.metadata import version
from json import JSONDecodeError
from typing import Any, AsyncContextManager, Callable, List, Mapping, Optional, cast

import httpx
import trio
from cattr import GenConverter
from httpx import URL, AsyncClient
from prettyprinter import cpprint
from trio.lowlevel import checkpoint

from matriisi.http.httpevents import (
    MatrixEventRoomCanonicalAlias,
    MatrixEventRoomCreate,
    MatrixEventRoomCreatePreviousRoom,
    MatrixEventRoomJoinRules,
    MatrixEventRoomMember,
    MatrixEventRoomMessage,
    MatrixEventRoomName,
    MatrixEventRoomTopic,
    MatrixHttpEvent,
    MatrixHttpEventContent,
    MatrixRoomBaseEvent,
    MatrixRoomBaseStateEvent,
    MatrixRoomEvent,
    MatrixRoomJoinRule,
    MatrixRoomMemberMembership,
    MatrixRoomStateEvent,
    MatrixUnknownEventContent,
)
from matriisi.http.structs import (
    MatrixJoinedRoom,
    MatrixPresence,
    MatrixRoomMessages,
    MatrixRoomSummary,
    MatrixSync,
    MatrixSyncRooms,
    MatrixTimeline,
    MatrixVersions,
    MatrixWhoami,
)
from matriisi.id_dict import IdentifierDict
from matriisi.identifier import IDENTIFIER_TYPE, Identifier
from matriisi.utils import asynccontextmanager

logger = logging.getLogger(__name__)

converter = GenConverter(prefer_attrib_converters=True)


class MatrixErrorCode(str, enum.Enum):
    """
    An enumeration of possible errors.
    """

    M_FORBIDDEN = "M_FORBIDDEN"
    M_UNKNOWN_TOKEN = "M_UNKNOWN_TOKEN"
    M_MISSING_TOKEN = "M_MISSING_TOKEN"
    M_BAD_JSON = "M_BAD_JSON"
    M_NOT_JSON = "M_NOT_JSON"
    M_NOT_FOUND = "M_NOT_FOUND"
    M_LIMIT_EXCEEDED = "M_LIMIT_EXCEEDED"
    M_UNKNOWN = "M_UNKNOWN"

    M_UNRECOGNIZED = "M_UNRECOGNIZED"
    M_UNAUTHORIZED = "M_UNAUTHORIZED"
    M_USER_DEACTIVATED = "M_USER_DEACTIVATED"
    M_USER_IN_USE = "M_USER_IN_USE"
    M_INVALID_USERNAME = "M_INVALID_USERNAME"
    M_ROOM_IN_USE = "M_ROOM_IN_USE"
    M_INVALID_ROOM_STATE = "M_INVALID_ROOM_STATE"
    M_SERVER_NOT_TRUSTED = "M_SERVER_NOT_TRUSTED"
    M_UNSUPPORTED_ROOM_VERSION = "M_UNSUPPORTED_ROOM_VERSION"
    M_INCOMPATIBLE_ROOM_VERSION = "M_INCOMPATIBLE_ROOM_VERSION"
    M_BAD_STATE = "M_BAD_STATE"
    M_GUEST_ACCESS_FORBIDDEN = "M_GUEST_ACCESS_FORBIDDEN"
    M_MISSING_PARAM = "M_MISSING_PARAM"
    M_INVALID_PARAM = "M_INVALID_PARAM"
    M_TOO_LARGE = "M_TOO_LARGE"
    M_EXCLUSIVE = "M_EXCLUSIVE"
    M_RESOURCE_LIMIT_EXCEEDED = "M_RESOURCE_LIMIT_EXCEEDED"
    M_CANNOT_LEAVE_SERVER_NOTICE_ROOM = "M_CANNOT_LEAVE_SERVER_NOTICE_ROOM"


class MatrixHttpException(httpx.HTTPError):
    """
    Raised when a HTTP error happens.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)

        self.message = message
        self.code = MatrixErrorCode(code)

    def __str__(self):
        return f"{self.code}: {self.message}"


# noinspection PyShadowingBuiltins
class MatrixHttp(object):
    """
    Primary API interface for interacting with the Matrix C<->S API.

    This is the publically low-level API for Matriisi. If you're building just a client, not a
    bot, this is the API you'll want to integrate with.
    """

    PATH_PREFIX = "/_matrix/client/"
    USER_AGENT = (
        f"Matriisi/({version('matriisi')} Python/" f"{'.'.join(map(str, sys.version_info[0:3]))}"
    )

    def __init__(self, session: AsyncClient):
        """
        Creates a new HTTP client.

        :param session: The :class:`.AsyncClient` used for making HTTP requests.
        """
        self._session = session
        self._authentication_token: Optional[str] = None

        self._custom_converters = {}

    def add_custom_converter(self, type: str, convert: Callable[[dict], MatrixHttpEventContent]):
        """
        Adds a custom converter

        :param type: The type of the event.
        :param convert: A callable that takes the full event dictionary (including non-content)
                        fields, and returns a :class:`.MatrixHttpEventContent` subclass.
        :return: Nothing.
        """

        self._custom_converters[type] = convert

    def set_auth_token(self, token: str):
        """
        Sets the authentication token. This is a setter method to avoid accidentally getting the
        auth token attribute.
        """

        self._authentication_token = token

    ## Parser Methods ##
    # These methods are soley responsible for turning returned events into Python-level objects.

    @staticmethod
    def _parse_room_create(content):
        creator = Identifier.parse(content["creator"])
        federate = content.get("m.federate", True)
        pred = content.get("predecessor", None)
        if pred:
            pred = MatrixEventRoomCreatePreviousRoom(**pred)

        return MatrixEventRoomCreate(
            creator=creator,
            m_federate=federate,
            predecessor=pred,
            room_version=content.get("room_version", "1"),
        )

    @staticmethod
    def _parse_room_message(content):
        text = content.pop("body")
        type = content.pop("msgtype")

        return MatrixEventRoomMessage(body=text, type=type, extra_data=content)

    @staticmethod
    def _parse_room_canonical_alias(content):
        alias = content.get("alias", None)
        aliases = content.get("alt_aliases", [])

        return MatrixEventRoomCanonicalAlias(alias, aliases)

    @staticmethod
    def _parse_room_join_rules(content):
        jr = MatrixRoomJoinRule(content["join_rule"])

        return MatrixEventRoomJoinRules(jr)

    @staticmethod
    def _parse_room_member(content):
        membership = MatrixRoomMemberMembership(content["membership"])
        is_direct = content.get("direct", False)
        displayname = content.get("displayname")
        avatar_url = content.get("avatar_url")
        reason = content.get("reason")

        return MatrixEventRoomMember(
            membership=membership,
            avatar_url=avatar_url,
            display_name=displayname,
            reason=reason,
            is_direct=is_direct,
        )

    @staticmethod
    def _parse_room_name(content):
        return MatrixEventRoomName(content["name"])

    @staticmethod
    def _parse_room_topic(content):
        return MatrixEventRoomTopic(content["topic"])

    def _parse_matrix_event(self, type_: str, event_content) -> MatrixHttpEventContent:
        """
        Parses a Matrix event. This is a hardcoded, super-function.
        """

        if type_ == "m.room.create":
            evt = self._parse_room_create(event_content)

        elif type_ == "m.room.member":
            evt = self._parse_room_member(event_content)

        elif type_ == "m.room.message":
            evt = self._parse_room_message(event_content)

        elif type_ == "m.room.canonical_alias":
            evt = self._parse_room_canonical_alias(event_content)

        elif type_ == "m.room.join_rules":
            evt = self._parse_room_join_rules(event_content)

        else:
            logger.warning(f"Encountered unknown built-in event type {type_}")
            return MatrixUnknownEventContent(event_content)

        return evt

    def _parse_custom_event(self, type_: str, event_content) -> MatrixHttpEventContent:
        """
        Parses a custom, unknown event.
        """
        converter = self._custom_converters.get(type_)
        if converter is None:
            logger.debug(f"Encountered unknown event {type_}, skipping")
            return MatrixUnknownEventContent(event_content)

        return converter(event_content)

    def _parse_event_content(self, type_: str, event_content) -> MatrixHttpEventContent:
        """
        Parses the content of an event.
        """
        if type_.startswith("m."):
            return self._parse_matrix_event(type_, event_content)
        else:
            return self._parse_custom_event(type_, event_content)

    def _parse_room_event(self, full_event, *, override_room_id: str = None) -> MatrixRoomBaseEvent:
        """
        Parses a room event.
        """
        type_: str = full_event["type"]
        sender = Identifier.parse(full_event["sender"])

        # stripped state events don't have event_id or origin_server_ts
        is_full_event = "event_id" in full_event

        content = self._parse_event_content(type_, full_event["content"])
        # sync state events don't have this...
        if override_room_id:
            room_id = override_room_id
        else:
            room_id = full_event["room_id"]

        if "state_key" in full_event:
            if not is_full_event:
                return MatrixRoomBaseStateEvent(
                    type=type_, content=content, sender=sender, state_key=full_event["state_key"]
                )

            # state event
            prev_content = full_event.get("prev_content")
            if prev_content is not None:
                prev_content = self._parse_event_content(full_event["type"], prev_content)

            event_id = full_event["event_id"]
            origin_timestamp = int(full_event["origin_server_ts"])

            evt = MatrixRoomStateEvent(
                type=type_,
                content=content,
                event_id=event_id,
                origin_timestamp=origin_timestamp,
                sender=sender,
                room_id=room_id,
                state_key=full_event["state_key"],
                prev_content=prev_content,
            )
        else:
            event_id = full_event["event_id"]
            origin_timestamp = int(full_event["origin_server_ts"])

            # full, non-state event
            evt = MatrixRoomEvent(
                type=type_,
                content=content,
                event_id=event_id,
                origin_timestamp=origin_timestamp,
                sender=sender,
                room_id=room_id,
            )

        return evt

    def _parse_simple_event(self, data) -> MatrixHttpEvent:
        """
        Parses a simple event.
        """
        type_ = data["type"]
        content = data["content"]

        return MatrixHttpEvent(type_, self._parse_event_content(type_, content))

    def _parse_room_timeline(self, data, room_id: str) -> MatrixTimeline:
        """
        Parses a timeline from room data.
        """
        events = cast(
            List[MatrixRoomEvent],
            [self._parse_room_event(event, override_room_id=room_id) for event in data["events"]],
        )

        return MatrixTimeline(
            events, limited=data.get("limited", False), prev_batch=data.get("prev_batch")
        )

    @staticmethod
    def _parse_room_summary(data):
        """
        Parses a room summary.
        """
        return MatrixRoomSummary(
            data.get("m.heroes", []),
            data.get("m.invited_member_count"),
            data.get("m.joined_member_count"),
        )

    def _parse_joined_rooms(self, data) -> IdentifierDict[MatrixJoinedRoom]:
        """
        Parses the joined rooms.
        """
        rooms = IdentifierDict()

        for room_id, room_data in data.items():
            state = cast(
                List[MatrixRoomStateEvent],
                [
                    self._parse_room_event(event, override_room_id=room_id)
                    for event in room_data["state"]["events"]
                ],
            )
            timeline = self._parse_room_timeline(room_data["timeline"], room_id)
            ad = [self._parse_simple_event(event) for event in room_data["account_data"]["events"]]
            ephemeral = [
                self._parse_simple_event(event) for event in room_data["ephemeral"]["events"]
            ]

            summary = room_data["summary"] or None
            if summary:
                summary = self._parse_room_summary(summary)

            obb = MatrixJoinedRoom(
                room_id=room_id,
                account_data=ad,
                state=state,
                timeline=timeline,  # type: ignore
                ephemeral=ephemeral,
                summary=summary,
            )
            rooms[Identifier.parse(room_id)] = obb

        return rooms

    def _parse_sync_rooms(self, data) -> MatrixSyncRooms:
        """
        Parses the ``rooms`` field of the sync payload.
        """
        joined = self._parse_joined_rooms(data["join"])

        return MatrixSyncRooms(invite=IdentifierDict(), joined=joined, leave=IdentifierDict())

    ## HTTP Methods ##

    async def _check_login(self):
        # this does exist
        await checkpoint()

        if self._authentication_token is None:
            callee = inspect.stack()[1]
            name = callee.function
            del callee

            raise RuntimeError(f"This function ({name}) requires authentication")

    async def matrix_request(
        self,
        method: str,
        path: str,
        query_params: Mapping[str, str] = None,
        body: Any = None,
    ) -> dict:
        """
        Makes a request to the Matrix server.

        :param method: The HTTP method to use.
        :param path: The path to use. If this has no leading slash, it is prefixed automatically.
        :param query_params: The query parameters to send.
        :param body: The HTTP body to use.
        :return: The body of the response, if any.
        """

        if not path.startswith("/"):
            path = self.PATH_PREFIX + path

        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        if self._authentication_token is not None:
            headers["Authorization"] = "Bearer " + self._authentication_token
        if body is not None:
            headers["Content-Type"] = "application/json; encoding=utf-8"

        for try_ in range(0, 5):
            logger.debug(f"{method} {path} -> <pending> (try {try_ + 1}/5)")

            resp = await self._session.request(
                method=method,
                url=path,
                headers=headers,
                params=query_params,
                json=body,
                allow_redirects=True,
                timeout=99999999,  # genuinely, fuck off
            )
            logger.debug(f"{method} {path} -> {resp.status_code} (try {try_ + 1}/5)")

            headers = resp.headers
            ct = headers["content-type"]
            if ct != "application/json":
                raise TypeError(f"Expected JSON response, got '{ct}'")

            body = resp.json()

            if 200 <= resp.status_code < 300:
                return body

            # no success, check error states
            error = body.get("errcode")
            if error is not None:
                logger.warning(f"Server error: {error}")

            # hardcode ratelimit
            if resp.status_code == 429 or error == MatrixErrorCode.M_LIMIT_EXCEEDED:
                # ratelimit, sleep
                ms = body.get("retry_after_ms")

                if ms is None:
                    # good assumption
                    await trio.sleep(0.5)
                else:
                    await trio.sleep(float(ms) / 1000)

                continue

            # server error
            if 500 <= resp.status_code < 600:
                sleep_time = (try_ + 1) * 0.5
                logger.warning(
                    f"Server error ({resp.status_code}), backing off for "
                    f"{sleep_time:.1f} seconds"
                )
                await trio.sleep(sleep_time)
                continue

            # client error
            if 400 <= resp.status_code < 500:
                raise MatrixHttpException(MatrixErrorCode(error), body.get("error"))

            raise RuntimeError(f"Don't know what to do with code {resp.status_code}")

    async def versions(self) -> MatrixVersions:
        """
        Gets the versions that the Matrix homeserver supports.
        """

        return converter.structure(await self.matrix_request("GET", "versions"), MatrixVersions)

    async def whoami(self) -> MatrixWhoami:
        """
        Checks who the owner of this token is.
        """
        result = await self.matrix_request("GET", "r0/account/whoami")
        return converter.structure(result, MatrixWhoami)

    async def login(self, identifier: str, password: str) -> str:
        """
        Logs in to the matrix homeserver.

        :param identifier: The user identifier or localpart.
        :param password: The password for the user.
        :return: The fully qualified Matrix ID for this account.
        """

        body = {
            "type": "m.login.password",
            "identifier": {
                "type": "m.id.user",
                "user": identifier,
            },
            "device_id": f"Matriisi",
            "initial_device_display_name": f"Matriisi Library",
            "password": password,
        }

        resp = await self.matrix_request("POST", "r0/login", body=body)
        access_token = resp["access_token"]
        self.set_auth_token(access_token)
        return resp["user_id"]

    async def sync(
        self,
        filter: str = None,
        full_state: bool = False,
        set_presence: MatrixPresence = None,
        since: str = None,
        timeout: int = 5000,
    ) -> MatrixSync:
        """
        Synchronises state between the client and the server.

        :param filter: Either the ID of a filter, or an object representing a matrix filter.
        :param full_state: If all state events will should returned. Default false. See the
                           `spec`_ for more information.
        :param set_presence: Controls the presence for this client. If unset, will use default
                             Matrix behaviour.
        :param since: A point in time to continue a sync. Can be obtained from ``next_batch``.
        :param timeout: The server-side timeout to wait, in milliseconds, before returning the
                        events. The default value (zero) will cause the sever to return
                        immediately.

                        It is recommended to use a Trio timeout block wrapping this as well for a
                        client-side timeout.

        :return: The sync data from the server.

        .. _spec: https://spec.matrix.org/unstable/client-server-api/#get_matrixclientr0sync
        """
        params = {"full_state": full_state, "timeout": str(timeout)}

        if filter is not None:
            params["filter"] = filter

        if set_presence is not None and set_presence != MatrixPresence.UNAVAILABLE:
            params["set_presence"] = set_presence.name.lower()

        if since is not None:
            params["since"] = since

        result = await self.matrix_request("GET", "r0/sync", query_params=params)

        # oh boy, this is a *lot* of parsing
        next_batch = result["next_batch"]

        account_data_raw = result.get("account_data")
        account_data = []

        if account_data_raw:
            account_data = [self._parse_simple_event(evt) for evt in account_data_raw["events"]]

        # room_data =
        room_data = result.get("rooms")
        if room_data:
            rooms = self._parse_sync_rooms(room_data)
        else:
            rooms = MatrixSyncRooms(
                invite=IdentifierDict(), joined=IdentifierDict(), leave=IdentifierDict()
            )

        return MatrixSync(
            next_batch,
            account_data=account_data,
            room_data=rooms,
        )

    async def get_events(
        self,
        room_id: IDENTIFIER_TYPE,
        from_token: str,
        reverse: bool = False,
        limit: int = 10,
        to_token: str = None,
    ) -> MatrixRoomMessages:
        """
        Gets the events for a room.

        :param room_id: The room to download events from.
        :param from_token: The token that marks the point in time to fetch events from.
        :param reverse: If the order should be reversed (newer events first).
        :param limit: The maximum number of events to download.
        :param to_token: The token to stop returning events at.
        :return: A list of events.
        """
        path = f"r0/rooms/{room_id}/messages"
        dir = "b" if reverse else "f"

        params = {
            "from": from_token,
            "dir": dir,
            "limit": limit,
        }

        if to_token is not None:
            params["to"] = to_token

        response = await self.matrix_request("GET", path, query_params=params)
        chunk = response.get("chunk", [])

        # these are never stripped state
        chunk_events = cast(
            List[MatrixRoomEvent],
            [self._parse_room_event(evt, override_room_id=room_id) for evt in chunk],
        )
        state = response.get("state", [])
        state_events = cast(
            List[MatrixRoomStateEvent],
            [self._parse_room_event(evt, override_room_id=room_id) for evt in state],
        )

        return MatrixRoomMessages(
            chunk=chunk_events,
            start=response["start"],
            end=response.get("end"),
            state=state_events,
        )

    async def send_event(
        self,
        room_id: IDENTIFIER_TYPE,
        event_type: str,
        body: Any,
        *,
        state_key: str = None,
        txnid: str = None,
    ) -> str:
        """
        Sends an event to a room.

        :param room_id: The :class:`.Identifier` or :class:`str` ID for the room.
        :param event_type: The event type to send, e.g. ``m.room.message``.
        :param body: The JSON content of the event.
        :param state_key: An optional state key. If this is not None, this will be a state event.
                          Set to the empty string if you don't want to provide one.
        :param txnid: The transaction ID. If None and ``state_key`` is None, will be automatically
                      generated.
        :return: The event ID for this event.
        """
        url = f"r0/rooms/{room_id}/"
        if state_key is not None:
            url += f"state/{event_type}"
            if state_key:
                url += f"/{state_key}"
        else:
            url += f"send/{event_type}/"
            if txnid is None:
                # 128 bits of entropy, virtually guarenteed to never repeat
                txnid = secrets.token_urlsafe(nbytes=8)

            url += txnid

        return (await self.matrix_request("PUT", url, body=body))["event_id"]


@asynccontextmanager
async def create_http_client(homeserver_hostname: str) -> AsyncContextManager[MatrixHttp]:
    """
    Creates an HTTP client, using the specified homeserver. This will look up the real location
    via ``.well-known`` if available.

    :param homeserver_hostname: The hostname of the homeserver.
    :return: A context manager that manages the Matrix HTTP client.
    """

    async with AsyncClient(
        timeout=99999999999999999,
        http2=True,
    ) as client:  # type: AsyncClient
        url = homeserver_hostname
        wk_url = f"https://{homeserver_hostname}/.well-known/matrix/client"
        resp = await client.get(wk_url, allow_redirects=True)

        if resp.status_code != 200:
            logger.debug(f".well-known returned {resp.status_code}")
        else:
            try:
                body = resp.json()
                url = body["m.homeserver"]["base_url"]
            except (KeyError, JSONDecodeError):
                logger.error(f".well-known had unknown body, ignoring")

        # force https if well_known returned http to avoid extra redirects
        url = URL(url).copy_with(scheme="https")
        client.base_url = url

        http = MatrixHttp(client)
        yield http
