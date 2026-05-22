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
    """
    AgentNode配置
    Fields:
        name: node名称
        agent_type: agent类型
        working_directory: agent工作目录
        [optional] executable_path: agent可执行文件路径
        [optional] system_prompt: agent的system_prompt
        [optional] model: agent使用的模型
        [optional] cli_args: 传给agent的CLI参数
        [optional] env: 传给agent的环境变量
        [optional] context_window_tokens: 上下文窗口长度
        [optional] max_turns: 对话轮数最大值
        [optional] turn_timeout_seconds: 每轮对话超时时间
        [optional] startup_timeout_seconds: agent启动超时时间
        [optional] semantic_inactivity_timeout_seconds: 后端无直接响应超时时间
        [optional] auto_start: 第一次使用时自动启动runtime
        [optional] targets: Langgraph中的下游节点
        [optional] prompt_prefix: 额外的prompt前缀
        [optional] folder_name: 指定.workflow/agent下配置的文件夹名
        [optional] persist_runtime_history: 是否保存runtime的所有对话历史
        [optional] persist_node_mailboxes: 是否保存每个node的mailbox历史（与其他node交互的历史）
        [optional] runtime_options: 额外的runtime配置
        [optional] instance_key: runtime实例的标识，可以由Registry保存并复用
    """

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
    persist_runtime_history: bool = False
    persist_node_mailboxes: bool = True
    runtime_options: dict[str, Any] = field(default_factory=dict)
    instance_key: str = field(default_factory=lambda: uuid4().hex)

    @classmethod
    def from_provider_defaults(
        cls,
        *,
        home_directory: str | Path | None = None,
        reuse_fields: tuple[str, ...] = ("model",),
        provider_config_directory: str | Path | None = None,
        **kwargs: Any,
    ) -> "AgentNodeConfig":
        """
        根据参数由本地agent配置复用一套配置到当前AgentNode
        Args:
            cls: 回调函数，在函数最后调用，参数为kwargs
            [optional] home_directory: home目录，用于搜索agent默认配置。默认使用Path.home获取
            [optional] reuse_fields: 哪些配置需要复用
            [optional] provider_config_directory: 目标Agent的配置文件夹
            [optional] kwargs: 主要有下列键值作用
                agent_type: agent类型
                working_directory: 目标Agent的配置文件夹
                model: agent使用的模型
                runtime_options: 作为返回值返回一些最终的配置项（目前为是否复用skill和mcp）
        """
        from .config_reuse import build_reused_agent_config

        agent_type = kwargs["agent_type"]
        actual_working_directory = kwargs["working_directory"]
        working_directory = provider_config_directory or actual_working_directory
        reused = build_reused_agent_config(
            agent_type=agent_type,
            working_directory=working_directory,
            reuse_fields=reuse_fields,
            home_directory=home_directory,
            include_home_defaults=provider_config_directory is None,
        )
        if (
            provider_config_directory is not None
            and Path(provider_config_directory).resolve() != Path(actual_working_directory).resolve()
            and not reused.model
            and not reused.skills
            and not reused.mcp
            and not reused.runtime_options
        ):
            reused = build_reused_agent_config(
                agent_type=agent_type,
                working_directory=actual_working_directory,
                reuse_fields=reuse_fields,
                home_directory=home_directory,
                include_home_defaults=True,
            )

        if not kwargs.get("model"):
            kwargs["model"] = reused.model

        runtime_options = dict(reused.runtime_options)
        if reused.skills:
            runtime_options.setdefault("reused_skills", list(reused.skills))
        if reused.mcp:
            runtime_options.setdefault("reused_mcp", dict(reused.mcp))
        runtime_options.update(dict(kwargs.get("runtime_options") or {}))
        kwargs["runtime_options"] = runtime_options
        return cls(**kwargs)

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
            "persist_runtime_history": self.persist_runtime_history,
            "persist_node_mailboxes": self.persist_node_mailboxes,
            "runtime_options": dict(self.runtime_options),
            "instance_key": self.instance_key,
        }
