from typing import Protocol, TypeVar, TypedDict, Any, ClassVar, NotRequired
from importlib import import_module

from django import forms
from django.db.models import QuerySet

from tracker.models import UserItem


class ToastPayload(TypedDict):
    id: int
    title: str
    url: NotRequired[str]
    kind: NotRequired[str]


class Action(Protocol):
    slug: ClassVar[str]  # machine id
    label: ClassVar[str]  # human-readable
    group: ClassVar[str]  # e.g. "selector", "bulk", etc.
    ParamForm: ClassVar[type[forms.Form]]

    def __call__(self, qs: QuerySet[UserItem], **params: Any) -> ToastPayload:
        """Return payload for toast (serializable to JSON)"""
        ...


# global registry
registry: dict[str, type[Action]] = {}

_T = TypeVar("_T", bound=Action)


def register(action_cls: type[_T]) -> type[_T]:
    """
    Decorator: register *class*, store a *single instance* in the registry,
    and return the class unchanged so normal class semantics remain.
    """
    registry[action_cls.slug] = action_cls

    return action_cls


# auto-import selectors
# assign to _ to avoid linter complaining
_ = import_module(".selectors", package=__name__)
_ = import_module(".bulk", package=__name__)
