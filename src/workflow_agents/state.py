from __future__ import annotations

from typing import Any, Annotated, TypedDict


def merge_mailboxes(
    left: dict[str, list[dict[str, Any]]] | None,
    right: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, list[dict[str, Any]]]:
    """Merge mailbox state by treating the right-hand side as the latest value per key."""
    merged: dict[str, list[dict[str, Any]]] = {key: list(items) for key, items in (left or {}).items()}
    for key, items in (right or {}).items():
        merged[key] = list(items)
    return merged


def merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """Merge two optional dictionaries with right-hand values taking precedence."""
    return {**(left or {}), **(right or {})}


class AgentGraphState(TypedDict, total=False):
    """Shared LangGraph state for workflows built from agent nodes."""

    mailboxes: Annotated[dict[str, list[dict[str, Any]]], merge_mailboxes]
    agent_results: Annotated[dict[str, dict[str, Any]], merge_dicts]
    shared: Annotated[dict[str, Any], merge_dicts]
