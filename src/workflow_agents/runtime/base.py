from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..storage import AgentWorkspace
from ..types import AgentNodeConfig, AgentOutputEvent, TokenUsageSnapshot, TurnResult, utc_now_iso


@dataclass(slots=True)
class _TurnContext:
    """每轮对话的上下文，包含一个TurnResult和标识是否完成的Event"""

    result: TurnResult
    completion: threading.Event = field(default_factory=threading.Event)


class ManagedAgentRuntime(ABC):
    """
    Agent运行时基类
    Args:
        config: AgentNode配置
        workspace: Agent对应的Workspace
    """

    def __init__(self, config: AgentNodeConfig, workspace: AgentWorkspace) -> None:
        """Initialize runtime state and restore any persisted session identifier."""
        self.config = config
        self.workspace = workspace
        self._lock = threading.RLock()
        self._current_turn: _TurnContext | None = None
        self._last_turn: TurnResult | None = None
        self._closed = False
        self._started = False
        self._session_id = ""
        self._load_runtime_state()

    def _load_runtime_state(self) -> None:
        """获取当前Agent的运行时状态（runtime.json的session_id）"""
        runtime_state = self.workspace.load_runtime_state()
        self._session_id = str(runtime_state.get("session_id", "") or "")

    def _persist_runtime_state(self) -> None:
        """保存当前session_id到runtime.json"""
        self.workspace.save_runtime_state({"session_id": self._session_id})

    @property
    def session_id(self) -> str:
        """Return the current persisted session or thread identifier."""
        with self._lock:
            return self._session_id

    def start(self) -> None:
        """启动Agent，实现由具体Agent后端的_start_impl"""
        with self._lock:
            if self._closed:
                raise RuntimeError(f"agent runtime {self.config.name} has been closed")
            if self._started:
                return
        self._start_impl()
        with self._lock:
            self._started = True

    def send_input(self, prompt: str) -> str:
        """
        向Agent发送一段prompt
        一次消息发送流程
        * 创建TurnResult记录一次会话
        * 创建TurnContext作为上下文管理，提供事件
        * 将当前会话记录到runtime.json
        * 调用_send_input_impl具体发送到agent，若发生错误调用_complete_turn完成一轮对话
        """
        if self.config.auto_start:
            self.start()
        with self._lock:
            if self._closed:
                raise RuntimeError(f"agent runtime {self.config.name} has been closed")
            if self._current_turn and not self._current_turn.completion.is_set():
                raise RuntimeError(f"agent runtime {self.config.name} already has an active turn")
            turn_result = TurnResult(
                turn_id=uuid4().hex,
                status="running",
                started_at=utc_now_iso(),
                usage=TokenUsageSnapshot(context_window_tokens=self.config.context_window_tokens),
                prompt=prompt,
            )
            turn_context = _TurnContext(result=turn_result)
            self._current_turn = turn_context
            self._append_runtime_history({"kind": "turn_started", "turn": turn_result.to_dict()})
        try:
            self._send_input_impl(prompt, turn_result.turn_id)
        except Exception as exc:
            self._complete_turn(turn_result.turn_id, status="failed", error=str(exc))
            raise
        return turn_result.turn_id

    def wait_for_completion(self, timeout: float | None = None) -> TurnResult:
        """等待上下文Event并返回一个TurnResult，若超时调用_cancel_active_turn取消本轮对话"""
        with self._lock:
            if self._current_turn is not None:
                turn_context = self._current_turn
            elif self._last_turn is not None:
                return TurnResult.from_dict(self._last_turn.to_dict())
            else:
                raise RuntimeError(f"agent runtime {self.config.name} has no active or completed turn")

        wait_timeout = timeout if timeout is not None else self.config.turn_timeout_seconds
        finished = turn_context.completion.wait(wait_timeout)
        if not finished:
            self._cancel_active_turn("turn timed out", "timeout")
            turn_context.completion.wait(5.0)

        with self._lock:
            snapshot = self._last_turn or turn_context.result
            return TurnResult.from_dict(snapshot.to_dict())

    def run_turn(self, prompt: str, timeout: float | None = None) -> TurnResult:
        """一个包装了send_input和wait_for_completion的工具函数"""
        self.send_input(prompt)
        return self.wait_for_completion(timeout=timeout)

    def is_output_complete(self) -> bool:
        """当前对话是否已完成"""
        with self._lock:
            if self._current_turn is None:
                return self._last_turn is not None
            return self._current_turn.completion.is_set()

    def get_output_events(self, after_index: int = 0) -> list[AgentOutputEvent]:
        """获取当前一轮对话或最后一轮对话的流事件"""
        with self._lock:
            target = self._current_turn.result if self._current_turn is not None else self._last_turn
            if target is None:
                return []
            return [AgentOutputEvent.from_dict(event.to_dict()) for event in target.events if event.index >= after_index]

    def get_output_text(self) -> str:
        """获取当前一轮对话或最后一轮对话的最终输出"""
        with self._lock:
            target = self._current_turn.result if self._current_turn is not None else self._last_turn
            return "" if target is None else target.final_output

    def get_context_usage(self) -> TokenUsageSnapshot:
        """获取当前一轮对话或最后一轮对话的token用量"""
        with self._lock:
            target = self._current_turn.result if self._current_turn is not None else self._last_turn
            if target is None:
                return TokenUsageSnapshot(context_window_tokens=self.config.context_window_tokens)
            return TokenUsageSnapshot.from_dict(target.usage.to_dict())

    def get_context_usage_ratio(self) -> float | None:
        """Return the token usage ratio against the configured context window."""
        return self.get_context_usage().usage_ratio()

    def shutdown(self) -> None:
        """关闭一个agent"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._shutdown_impl()

    def _record_event(
        self,
        turn_id: str,
        event_type: str,
        *,
        content: str = "",
        call_id: str = "",
        tool_name: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """将当前一轮事件保存到运行时记录中"""
        with self._lock:
            if self._current_turn is None or self._current_turn.result.turn_id != turn_id:
                return
            event = AgentOutputEvent(
                event_type=event_type,
                content=content,
                call_id=call_id,
                tool_name=tool_name,
                payload=dict(payload or {}),
                index=len(self._current_turn.result.events),
            )
            self._current_turn.result.events.append(event)
            if event_type == "text" and content:
                self._current_turn.result.final_output += content
            self._append_runtime_history({"kind": "event", "turn_id": turn_id, "event": event.to_dict()})

    def _replace_usage(self, turn_id: str, usage: TokenUsageSnapshot) -> None:
        """Replace token usage for the specified active turn."""
        with self._lock:
            if self._current_turn is None or self._current_turn.result.turn_id != turn_id:
                return
            self._current_turn.result.usage = TokenUsageSnapshot.from_dict(usage.to_dict())

    def _merge_usage(self, turn_id: str, usage: TokenUsageSnapshot) -> None:
        """Accumulate token usage into the specified active turn."""
        with self._lock:
            if self._current_turn is None or self._current_turn.result.turn_id != turn_id:
                return
            current = self._current_turn.result.usage
            current.input_tokens += usage.input_tokens
            current.output_tokens += usage.output_tokens
            current.cache_read_tokens += usage.cache_read_tokens
            current.cache_write_tokens += usage.cache_write_tokens
            if usage.context_window_tokens:
                current.context_window_tokens = usage.context_window_tokens

    def _set_session_id(self, session_id: str) -> None:
        """Persist a new session or thread identifier for later reuse."""
        if not session_id:
            return
        with self._lock:
            self._session_id = session_id
            self._persist_runtime_state()

    def _set_final_output(self, turn_id: str, final_output: str) -> None:
        """获取当前一轮对话或最后一轮对话的final_output"""
        with self._lock:
            if self._current_turn is None or self._current_turn.result.turn_id != turn_id:
                return
            self._current_turn.result.final_output = final_output

    def _complete_turn(
        self,
        turn_id: str,
        *,
        status: str,
        final_output: str | None = None,
        error: str = "",
        session_id: str | None = None,
        usage: TokenUsageSnapshot | None = None,
    ) -> None:
        """会话准备结束，保存相应的历史信息，并设置对应事件"""
        with self._lock:
            if self._current_turn is None or self._current_turn.result.turn_id != turn_id:
                return
            turn_context = self._current_turn
            turn_context.result.status = status
            turn_context.result.error = error
            turn_context.result.completed_at = utc_now_iso()
            if final_output is not None:
                turn_context.result.final_output = final_output
            if session_id:
                turn_context.result.session_id = session_id
                self._session_id = session_id
                self._persist_runtime_state()
            if usage is not None:
                turn_context.result.usage = TokenUsageSnapshot.from_dict(usage.to_dict())
            self._last_turn = TurnResult.from_dict(turn_context.result.to_dict())
            self._current_turn = None
            self._append_runtime_history({"kind": "turn_completed", "turn": self._last_turn.to_dict()})
            turn_context.completion.set()

    def _append_runtime_history(self, payload: dict[str, Any]) -> None:
        """Persist runtime-level transcript data when history persistence is enabled."""
        if not self.config.persist_runtime_history:
            return
        self.workspace.append_jsonl(self.workspace.history_path, payload)

    @abstractmethod
    def _start_impl(self) -> None:
        """Backend-specific startup hook."""
        raise NotImplementedError

    @abstractmethod
    def _send_input_impl(self, prompt: str, turn_id: str) -> None:
        """Backend-specific implementation for sending prompt input."""
        raise NotImplementedError

    @abstractmethod
    def _cancel_active_turn(self, reason: str, status: str) -> None:
        """Backend-specific implementation for cancelling the active turn."""
        raise NotImplementedError

    @abstractmethod
    def _shutdown_impl(self) -> None:
        """Backend-specific shutdown hook."""
        raise NotImplementedError
