from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


AgentKind = Literal["claude", "claude_sdk", "codex"]
TurnStatus = Literal["running", "completed", "failed", "aborted", "timeout"]
EventType = Literal["text", "thinking", "tool_use", "tool_result", "status", "error", "log"]


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class TokenUsageSnapshot:
    """Token usage counters for a single agent turn."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    context_window_tokens: int | None = None

    def total_tokens(self) -> int:
        """Return the total counted tokens across all buckets."""
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens

    def usage_ratio(self) -> float | None:
        """Return the usage ratio against the configured context window."""
        if not self.context_window_tokens or self.context_window_tokens <= 0:
            return None
        return self.total_tokens() / self.context_window_tokens

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snapshot to a plain dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "context_window_tokens": self.context_window_tokens,
            "total_tokens": self.total_tokens(),
            "usage_ratio": self.usage_ratio(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TokenUsageSnapshot":
        """Build a snapshot from a persisted dictionary."""
        payload = payload or {}
        return cls(
            input_tokens=int(payload.get("input_tokens", 0) or 0),
            output_tokens=int(payload.get("output_tokens", 0) or 0),
            cache_read_tokens=int(payload.get("cache_read_tokens", 0) or 0),
            cache_write_tokens=int(payload.get("cache_write_tokens", 0) or 0),
            context_window_tokens=payload.get("context_window_tokens"),
        )


@dataclass(slots=True)
class AgentOutputEvent:
    """A single streaming event emitted by a managed agent runtime."""

    event_type: EventType
    content: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    call_id: str = ""
    tool_name: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    index: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event to a plain dictionary."""
        return {
            "event_type": self.event_type,
            "content": self.content,
            "created_at": self.created_at,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "payload": self.payload,
            "index": self.index,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentOutputEvent":
        """Build an event from a persisted dictionary."""
        return cls(
            event_type=payload["event_type"],
            content=payload.get("content", ""),
            created_at=payload.get("created_at", utc_now_iso()),
            call_id=payload.get("call_id", ""),
            tool_name=payload.get("tool_name", ""),
            payload=dict(payload.get("payload", {}) or {}),
            index=int(payload.get("index", 0) or 0),
        )


@dataclass(slots=True)
class InterNodeMessage:
    """A mailbox message exchanged between LangGraph nodes."""

    sender: str
    recipient: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to a plain dictionary."""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InterNodeMessage":
        """Build a mailbox message from a persisted dictionary."""
        return cls(
            sender=payload["sender"],
            recipient=payload["recipient"],
            content=payload["content"],
            metadata=dict(payload.get("metadata", {}) or {}),
            message_id=payload.get("message_id", uuid4().hex),
            created_at=payload.get("created_at", utc_now_iso()),
        )


@dataclass(slots=True)
class TurnResult:
    """Final result for a single agent turn."""

    turn_id: str
    status: TurnStatus
    started_at: str
    completed_at: str | None = None
    session_id: str = ""
    final_output: str = ""
    error: str = ""
    usage: TokenUsageSnapshot = field(default_factory=TokenUsageSnapshot)
    events: list[AgentOutputEvent] = field(default_factory=list)
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the turn result to a plain dictionary."""
        return {
            "turn_id": self.turn_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "session_id": self.session_id,
            "final_output": self.final_output,
            "error": self.error,
            "usage": self.usage.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "prompt": self.prompt,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TurnResult":
        """Build a turn result from a persisted dictionary."""
        return cls(
            turn_id=payload["turn_id"],
            status=payload["status"],
            started_at=payload["started_at"],
            completed_at=payload.get("completed_at"),
            session_id=payload.get("session_id", ""),
            final_output=payload.get("final_output", ""),
            error=payload.get("error", ""),
            usage=TokenUsageSnapshot.from_dict(payload.get("usage")),
            events=[AgentOutputEvent.from_dict(item) for item in payload.get("events", [])],
            prompt=payload.get("prompt", ""),
        )


@dataclass(slots=True)
class AgentNodeConfig:
    """Configuration for a long-lived agent node runtime."""

    name: str
    agent_type: AgentKind
    working_directory: str
    executable_path: str | None = None
    system_prompt: str = ""
    model: str = ""
    cli_args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    context_window_tokens: int | None = None
    max_turns: int | None = None
    turn_timeout_seconds: float = 1200.0
    startup_timeout_seconds: float = 30.0
    semantic_inactivity_timeout_seconds: float = 600.0
    auto_start: bool = True
    targets: tuple[str, ...] = ()
    prompt_prefix: str = ""
    folder_name: str | None = None
    runtime_options: dict[str, Any] = field(default_factory=dict)
    instance_key: str = field(default_factory=lambda: uuid4().hex)

    def normalized_working_directory(self) -> Path:
        """Return the absolute working directory for the agent."""
        return Path(self.working_directory).resolve()

    def to_persistable_dict(self) -> dict[str, Any]:
        """Serialize the config for durable storage."""
        return {
            "name": self.name,
            "agent_type": self.agent_type,
            "working_directory": str(self.normalized_working_directory()),
            "executable_path": self.executable_path,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "cli_args": list(self.cli_args),
            "env": dict(self.env),
            "context_window_tokens": self.context_window_tokens,
            "max_turns": self.max_turns,
            "turn_timeout_seconds": self.turn_timeout_seconds,
            "startup_timeout_seconds": self.startup_timeout_seconds,
            "semantic_inactivity_timeout_seconds": self.semantic_inactivity_timeout_seconds,
            "targets": list(self.targets),
            "prompt_prefix": self.prompt_prefix,
            "folder_name": self.folder_name,
            "runtime_options": dict(self.runtime_options),
            "instance_key": self.instance_key,
        }
