from __future__ import annotations

from typing import Union

try:
    import regex as re
except ModuleNotFoundError:
    import re

import attr

# TODO: Validate Server Name properly
IDENTIFIER_REGEXP = re.compile(r"(?P<localpart>[a-zA-Z0-9._=z\-/]{1,255}):(?P<domain>.+)")
VALID_SIGILS = {"@", "!", "$", "+", "#"}


@attr.s(slots=True, frozen=True, eq=False)
class Identifier(object):
    """
    An identifier consists of two parts: a local part, and a domain.
    """

    #: The sigil for this identifier.
    sigil: str = attr.ib()

    #: The localpart of the identifier. This is an opaque identifier for a single thing, such as a
    #: channel or a user.
    localpart: str = attr.ib()

    #: The domain of the identifier. This is the server name of the homeserver that allocated the
    #: identifier.
    domain: str = attr.ib()

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        if isinstance(other, str):
            return str(self) == other
        elif isinstance(other, Identifier):
            return (
                self.sigil == other.sigil
                and self.localpart == other.localpart
                and self.domain == other.domain
            )

        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return f"{self.sigil}{self.localpart}:{self.domain}"

    @classmethod
    def parse(cls, id: Union[str, Identifier]) -> Identifier:
        """
        Parses an identifier.

        :param id: The identifier to parse.
        :return: A new :class:`.Identifier`.
        """
        if isinstance(id, Identifier):
            return id

        sigil, rest = id[0], id[1:]
        if sigil not in VALID_SIGILS:
            raise ValueError(f"'{id}' has invalid sigil")

        match = IDENTIFIER_REGEXP.match(rest)
        if not match:
            raise ValueError(f"'{sigil}{rest}' is not a valid identifier")

        return Identifier(sigil=sigil, **match.groupdict())


IDENTIFIER_TYPE = Union[str, Identifier]
