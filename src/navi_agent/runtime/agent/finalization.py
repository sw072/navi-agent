"""Small, provider-independent fallbacks for ending an exhausted turn."""

from __future__ import annotations

from collections.abc import Callable

from ..models import Message

ITERATION_LIMIT_PROMPT = (
    "You've reached the maximum number of tool-calling iterations allowed. "
    "Provide a final response summarizing what you found and accomplished so far, "
    "without calling any more tools."
)


def request_iteration_summary(
    *,
    append_message: Callable[[Message], None],
    prepare: Callable[[], None],
    invoke: Callable[[], object],
    record: Callable[[object], None],
) -> object | None:
    """Make one tools-disabled final response request, like Hermes."""
    append_message(Message(role="user", content=ITERATION_LIMIT_PROMPT))
    prepare()
    response = invoke()
    record(response)
    return response
