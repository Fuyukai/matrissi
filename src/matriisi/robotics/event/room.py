from __future__ import annotations

import attr

from matriisi.dataclasses.member import RoomMember
from matriisi.dataclasses.room import Room
from matriisi.identifier import Identifier
from matriisi.robotics.event.base import Event

__all__ = (
    "RoomMeJoinedEvent",
    "RoomMemberJoinedEvent",
    "RoomMemberLeftEvent",
    "RoomMemberBannedEvent",
    "RoomMemberKickedEvent",
    "RoomMemberInviteRejectedEvent",
    "RoomMemberInviteRevokedEvent",
)


@attr.s(frozen=True, slots=True)
class RoomMeJoinedEvent(Event):
    """
    Fired when a room is joined by the current user.
    """

    insignificant = False

    #: The room being joined.
    room: Room = attr.ib()


@attr.s(frozen=True, slots=True)
class RoomMemberInvitedEvent(Event):
    """
    Fires when a member is invited to a room.
    """

    insignificant = False

    #: The room being invited to.
    room: Room = attr.ib()

    #: The ID of the member being invited.
    invitee_id: Identifier = attr.ib()

    #: The ID of the member who invited.
    inviter_id: Identifier = attr.ib()

    @property
    def inviter(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` that sent the invite.
        """

        return self.room.member(self.inviter_id)


@attr.s(frozen=True, slots=True)
class RoomMemberJoinedEvent(Event):
    """
    Fires when a room is joined by any user.
    """

    insignificant = False

    #: The room being joined.
    room: Room = attr.ib()

    #: The ID of the member joining.
    member_id: Identifier = attr.ib()

    #: If this member was previously invited.
    was_invited: bool = attr.ib(default=False)

    @property
    def member(self) -> RoomMember:
        """
        :return: The member object for this event.
        """

        return self.room.member(self.member_id)


@attr.s(frozen=True, slots=True)
class RoomMemberInviteRejectedEvent(Event):
    """
    Fires when an invite is rejected by a user.
    """

    insignificant = False

    #: The room the invite was for.
    room: Room = attr.ib()

    #: The ID of the member rejecting the invite.
    invited_id: Identifier = attr.ib()


@attr.s(frozen=True, slots=True)
class RoomMemberInviteRevokedEvent(Event):
    """
    Fires when an invite is revoked in a room.
    """

    insignificant = False

    #: The room the invite was for.
    room: Room = attr.ib()

    #: The ID of the member who was formely invitedd.
    invited_id: Identifier = attr.ib()

    #: The ID of the member who revoked the invite.
    revoker_id: Identifier = attr.ib()

    @property
    def revoker(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` that revoked the invite.
        """

        return self.room.member(self.revoker_id)


@attr.s(frozen=True, slots=True)
class RoomMemberBannedEvent(Event):
    """
    Fires when a member is banned.
    """

    insignificant = False

    #: The room the member is being banned from.
    room: Room = attr.ib()

    #: The ID of the member that is being banned.
    banned_id: Identifier = attr.ib()

    #: The ID of the member who did the ban.
    banner_id: Identifier = attr.ib()

    #: If the user was previously in the room. This will be False if the member was invited then
    #: banned, for example.
    was_in_room: bool = attr.ib(default=False)

    @property
    def banner(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` who performed the ban.
        """

        return self.room.member(self.banner_id)


@attr.s(frozen=True, slots=True)
class RoomMemberLeftEvent(Event):
    """
    Fires when a member leaves a room.
    """

    insignificant = False

    #: The room the member is leaving.
    room: Room = attr.ib()

    #: The ID of the member that is leaving.
    member_id: Identifier = attr.ib()


@attr.s(frozen=True, slots=True)
class RoomMemberKickedEvent(Event):
    """
    Fires when a member is kicked.
    """

    insignificant = False

    #: The room the member is leaving.
    room: Room = attr.ib()

    #: The ID of the member who is leaving.
    kicked_id: Identifier = attr.ib()

    #: The ID of the member who performed the kick.
    kicker_id: Identifier = attr.ib()

    @property
    def kicker(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` who performed the kick.
        """

        return self.room.member(self.kicker_id)


@attr.s(frozen=True, slots=True)
class RoomMemberUnbannedEvent(Event):
    """
    Fires when a member is unbanned.
    """

    insignificant = False

    #: The room the member is being unbanned from.
    room: Room = attr.ib()

    #: The ID of the member who is being unbanned.
    unbanned_id: Identifier = attr.ib()

    #: Thee ID of the member who performed the unban.
    unbanner_id: Identifier = attr.ib()

    @property
    def banner(self) -> RoomMember:
        """
        :return: The :class:`.RoomMember` who performed the ban.
        """

        return self.room.member(self.unbanner_id)
