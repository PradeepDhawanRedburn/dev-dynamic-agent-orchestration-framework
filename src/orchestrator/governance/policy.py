"""Rules enforced on graph state (ADR-0018, ADR-0033 points 4 and 7).

Graph state is checkpointed, and checkpoints keep strings and numbers unencrypted (spike S-17).
So a state model may hold identifiers, statuses and counters only: no requirement text, prompt,
result, answer or personal data is ever a state value. `free_text_fields` finds the fields that
break the rule, and a test applies it to every class registered with `@state_model`.

Allowed: `int`, `bool`, an enumeration, a `Literal` of strings or numbers, `Identifier` (a
pattern-checked token), and lists, sets, tuples, dicts, unions and nested state models of those.
Everything else is refused, including plain `str`, `float`, `Any` and bare `dict`.
"""

import types
from collections.abc import Mapping, Sequence, Set
from enum import Enum
from typing import (
    Annotated,
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from pydantic import BaseModel, StringConstraints

STATE_MODELS: list[type[Any]] = []


def state_model[T: type[Any]](cls: T) -> T:
    """Register a graph state model so the free-text test covers it."""
    STATE_MODELS.append(cls)
    return cls


def free_text_fields(model: type[Any]) -> list[str]:
    """Every field of `model` (and of state models nested in it) that could hold free text."""
    return _model_problems(model, prefix="", seen=set())


def _model_problems(model: type[Any], *, prefix: str, seen: set[type[Any]]) -> list[str]:
    if model in seen:
        return []
    seen.add(model)
    problems: list[str] = []
    for name, annotation in get_type_hints(model, include_extras=True).items():
        for reason in _violations(annotation, seen):
            problems.append(f"{prefix}{name}: {reason}")
    return problems


def _violations(annotation: Any, seen: set[type[Any]]) -> list[str]:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        base, *metadata = args
        if base is str:
            ok = any(isinstance(m, StringConstraints) and m.pattern for m in metadata)
            return [] if ok else ["a string without a pattern can hold free text"]
        return _violations(base, seen)
    if annotation in (int, bool, None, type(None)):
        return []
    if annotation is str:
        return ["a plain string can hold free text; use Identifier, a Literal or an enumeration"]
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return []
    if origin is Literal:
        ok = all(isinstance(a, str | int | bool) for a in args)
        return [] if ok else ["a Literal must hold strings or numbers"]
    if origin in (Union, types.UnionType):
        return [reason for arg in args for reason in _violations(arg, seen)]
    if isinstance(origin, type) and issubclass(origin, Mapping):
        if len(args) != 2:
            return ["a dict must say what it holds"]
        return [reason for arg in args for reason in _violations(arg, seen)]
    if isinstance(origin, type) and issubclass(origin, Sequence | Set):
        if not args:
            return ["a collection must say what it holds"]
        return [reason for arg in args if arg is not Ellipsis for reason in _violations(arg, seen)]
    if isinstance(annotation, type) and (
        issubclass(annotation, BaseModel) or is_typeddict(annotation)
    ):
        nested = _model_problems(annotation, prefix=f"{annotation.__name__}.", seen=seen)
        return nested
    return [f"{annotation!r} is not allowed in state"]
