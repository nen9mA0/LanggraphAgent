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
    """In-memory bookkeeping for the currently running turn."""

    result: TurnResult
    completion: threading.Event = field(default_factory=threading.Event)


class ManagedAgentRuntime(ABC):
    """Abstract base class for long-lived agent runtimes backed by CLI processes."""

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
        """Restore persisted runtime metadata from disk."""
        runtime_state = self.workspace.load_runtime_state()
        self._session_id = str(runtime_state.get("session_id", "") or "")

    def _persist_runtime_state(self) -> None:
        """Persist runtime metadata needed to resume future turns."""
        self.workspace.save_runtime_state({"session_id": self._session_id})

    @property
    def session_id(self) -> str:
        """Return the current persisted session or thread identifier."""
        with self._lock:
            return self._session_id

    def start(self) -> None:
        """Start the backing runtime if it is not already started."""
        with self._lock:
            if self._closed:
                raise RuntimeError(f"agent runtime {self.config.name} has been closed")
            if self._started:
                return
        self._start_impl()
        with self._lock:
            self._started = True

    def send_input(self, prompt: str) -> str:
        """Start a new turn by sending input to the backing agent runtime."""
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
        """Wait for the current turn to finish and return an immutable snapshot."""
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
        """Convenience wrapper that sends input and waits for completion."""
        self.send_input(prompt)
        return self.wait_for_completion(timeout=timeout)

    def is_output_complete(self) -> bool:
        """Report whether the current turn has fully completed."""
        with self._lock:
            if self._current_turn is None:
                return self._last_turn is not None
            return self._current_turn.completion.is_set()

    def get_output_events(self, after_index: int = 0) -> list[AgentOutputEvent]:
        """Return recorded output events for the active or most recent turn."""
        with self._lock:
            target = self._current_turn.result if self._current_turn is not None else self._last_turn
            if target is None:
                return []
            return [AgentOutputEvent.from_dict(event.to_dict()) for event in target.events if event.index >= after_index]

    def get_output_text(self) -> str:
        """Return the final accumulated text for the active or most recent turn."""
        with self._lock:
            target = self._current_turn.result if self._current_turn is not None else self._last_turn
            return "" if target is None else target.final_output

    def get_context_usage(self) -> TokenUsageSnapshot:
        """Return token usage for the active or most recent turn."""
        with self._lock:
            target = self._current_turn.result if self._current_turn is not None else self._last_turn
            if target is None:
                return TokenUsageSnapshot(context_window_tokens=self.config.context_window_tokens)
            return TokenUsageSnapshot.from_dict(target.usage.to_dict())

    def get_context_usage_ratio(self) -> float | None:
        """Return the token usage ratio against the configured context window."""
        return self.get_context_usage().usage_ratio()

    def shutdown(self) -> None:
        """Shut down the runtime and release external resources."""
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
        """Record a streaming event for the currently running turn."""
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
        """Override the final text buffer for the specified active turn."""
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
        """Finalize the specified turn and persist its completed snapshot."""
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
