from collections.abc import Mapping
from typing import (
    AbstractSet,
    Generic,
    Iterator,
    MutableMapping,
    Optional,
    Tuple,
    TypeVar,
    Union,
    ValuesView,
)

from matriisi.identifier import Identifier

T = TypeVar("T")
V = TypeVar("V")


class IdentifierDict(MutableMapping[Identifier, T], Generic[T]):
    """
    A dict that maps Identifier -> T, allowing look up by string name, too.
    """

    def __init__(self, others: Mapping[Identifier, T] = None):
        self._others = {}
        if others:
            self._others.update(others)

    def __setitem__(self, k: Identifier, v: T) -> None:
        self._others[k] = v

    def __delitem__(self, v: Identifier) -> None:
        del self._others[v]

    def __getitem__(self, k: Identifier) -> T:
        return self._others[k]

    def __len__(self) -> int:
        return len(self._others)

    def __iter__(self) -> Iterator[T]:
        return iter(self._others)

    def keys(self) -> AbstractSet[T]:
        return self._others.keys()

    def values(self) -> ValuesView[T]:
        return self._others.values()

    def items(self) -> AbstractSet[Tuple[Identifier, T]]:
        return self._others.items()

    def get(self, key: Identifier) -> Optional[T]:
        return self._others.get(key)

    def get_by_str(self, item: str, default: V = None) -> Union[T, V]:
        """
        Gets an item by name.
        """
        id = Identifier.parse(item)
        return self._others.get(item, default)

    def __str__(self):
        return str(self._others)

    def __repr__(self):
        return repr(self._others)


try:
    from prettyprinter import register_pretty
except ImportError:
    pass
else:
    from prettyprinter.prettyprinter import pretty_dict

    @register_pretty(IdentifierDict)
    def _pretty_iddict(d, ctx, trailing_comment=None):
        return pretty_dict(d, ctx, trailing_comment=trailing_comment)
