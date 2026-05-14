from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any

from ..types import AgentNodeConfig, TokenUsageSnapshot
from .base import ManagedAgentRuntime


class CodexRuntime(ManagedAgentRuntime):
    """Managed runtime that talks to Codex through its JSON-RPC app-server."""

    def __init__(self, config: AgentNodeConfig, workspace) -> None:
        """Initialize Codex runtime process and RPC bookkeeping."""
        super().__init__(config, workspace)
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._request_id = 0
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._rpc_lock = threading.RLock()
        self._thread_id = self.session_id
        self._active_turn_id = ""

    def _start_impl(self) -> None:
        """Start the Codex app-server and initialize or resume a thread."""
        executable = self.config.executable_path or "codex"
        if shutil.which(executable) is None and not Path(executable).exists():
            raise FileNotFoundError(f"codex executable not found: {executable}")

        process = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://", *self.config.cli_args],
            cwd=str(self.config.normalized_working_directory()),
            env={**os.environ, **self.config.env},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._process = process
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

        self._rpc_request(
            "initialize",
            {
                "clientInfo": {"name": "workflow_agents", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
            timeout=self.config.startup_timeout_seconds,
        )
        self._rpc_notify("initialized")

        if self._thread_id:
            try:
                response = self._rpc_request(
                    "thread/resume",
                    {
                        "threadId": self._thread_id,
                        "cwd": str(self.config.normalized_working_directory()),
                        "model": self.config.model or None,
                        "developerInstructions": self.config.system_prompt or None,
                    },
                    timeout=self.config.startup_timeout_seconds,
                )
                self._thread_id = (((response or {}).get("thread")) or {}).get("id", self._thread_id)
            except Exception:
                self._thread_id = ""

        if not self._thread_id:
            response = self._rpc_request(
                "thread/start",
                {
                    "model": self.config.model or None,
                    "cwd": str(self.config.normalized_working_directory()),
                    "developerInstructions": self.config.system_prompt or None,
                    "persistExtendedHistory": True,
                },
                timeout=self.config.startup_timeout_seconds,
            )
            self._thread_id = (((response or {}).get("thread")) or {}).get("id", "")
            if not self._thread_id:
                raise RuntimeError("codex thread/start returned no thread id")
            self._set_session_id(self._thread_id)

    def _send_input_impl(self, prompt: str, turn_id: str) -> None:
        """Send a new ``turn/start`` request to the active Codex thread."""
        if not self._thread_id:
            raise RuntimeError("codex thread not initialized")
        self._active_turn_id = turn_id
        self._rpc_request(
            "turn/start",
            {
                "threadId": self._thread_id,
                "input": [{"type": "text", "text": prompt}],
            },
            timeout=self.config.startup_timeout_seconds,
        )

    def _rpc_notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification to the Codex app-server."""
        self._write_rpc({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _rpc_request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for its response."""
        with self._rpc_lock:
            self._request_id += 1
            request_id = self._request_id
            response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = response_queue
        self._write_rpc({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            payload = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._rpc_lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"codex request timed out: {method}") from exc
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload.get("result", {})

    def _write_rpc(self, payload: dict[str, Any]) -> None:
        """Write one JSON-RPC message to the Codex stdin transport."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("codex process is not running")
        self._process.stdin.write(json.dumps(payload, ensure_ascii=True))
        self._process.stdin.write("\n")
        self._process.stdin.flush()

    def _reader_loop(self) -> None:
        """Read stdout lines from Codex and dispatch RPC responses or notifications."""
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if "id" in payload and ("result" in payload or "error" in payload):
                    self._handle_response(payload)
                elif "method" in payload:
                    self._handle_notification(payload)
        finally:
            with self._rpc_lock:
                for response_queue in self._pending.values():
                    response_queue.put({"error": "codex process exited"})
                self._pending.clear()

    def _stderr_loop(self) -> None:
        """Capture a bounded tail of Codex stderr output for diagnostics."""
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            text = line.rstrip()
            if text:
                self._stderr_tail.append(text)

    def _handle_response(self, payload: dict[str, Any]) -> None:
        """Resolve a pending JSON-RPC request from a response payload."""
        request_id = int(payload["id"])
        with self._rpc_lock:
            response_queue = self._pending.pop(request_id, None)
        if response_queue is None:
            return
        if "error" in payload:
            error = payload["error"]
            if isinstance(error, dict):
                error = error.get("message", json.dumps(error, ensure_ascii=True))
            response_queue.put({"error": str(error)})
        else:
            response_queue.put({"result": payload.get("result", {})})

    def _handle_notification(self, payload: dict[str, Any]) -> None:
        """Handle Codex notifications and convert them into runtime events."""
        method = payload.get("method", "")
        params = payload.get("params", {}) or {}
        if method == "turn/started":
            self._record_event(self._active_turn_id, "status", content="running")
            return
        if method == "turn/completed":
            turn = params.get("turn", {}) or {}
            usage = turn.get("usage", {}) or {}
            status = turn.get("status", "completed")
            final_status = "completed"
            final_error = ""
            if status in {"failed"}:
                final_status = "failed"
                final_error = (((turn.get("error") or {}).get("message")) if isinstance(turn.get("error"), dict) else "") or "codex turn failed"
            elif status in {"cancelled", "canceled", "aborted", "interrupted"}:
                final_status = "aborted"
                final_error = "codex turn aborted"
            self._complete_turn(
                self._active_turn_id,
                status=final_status,
                error=final_error,
                session_id=self._thread_id,
                usage=TokenUsageSnapshot(
                    input_tokens=int(usage.get("input_tokens", 0) or 0),
                    output_tokens=int(usage.get("output_tokens", 0) or 0),
                    cache_read_tokens=int(usage.get("cache_read_tokens", 0) or 0),
                    cache_write_tokens=int(usage.get("cache_write_tokens", 0) or 0),
                    context_window_tokens=self.config.context_window_tokens,
                ),
            )
            self._active_turn_id = ""
            return
        if not method.startswith("item/"):
            return
        item = params.get("item", {}) or {}
        item_type = item.get("type")
        item_id = item.get("id", "")
        if method == "item/started" and item_type == "commandExecution":
            self._record_event(
                self._active_turn_id,
                "tool_use",
                call_id=item_id,
                tool_name="exec_command",
                payload={"command": item.get("command", "")},
            )
        elif method == "item/completed" and item_type == "commandExecution":
            self._record_event(
                self._active_turn_id,
                "tool_result",
                call_id=item_id,
                tool_name="exec_command",
                content=item.get("aggregatedOutput", ""),
            )
        elif method == "item/started" and item_type == "fileChange":
            self._record_event(self._active_turn_id, "tool_use", call_id=item_id, tool_name="patch_apply")
        elif method == "item/completed" and item_type == "fileChange":
            self._record_event(self._active_turn_id, "tool_result", call_id=item_id, tool_name="patch_apply")
        elif method == "item/completed" and item_type == "agentMessage":
            text = item.get("text", "")
            if text:
                self._record_event(self._active_turn_id, "text", content=text)
                self._set_final_output(self._active_turn_id, text)

    def _cancel_active_turn(self, reason: str, status: str) -> None:
        """Terminate the active Codex turn and finalize it with the given status."""
        active_turn_id = self._active_turn_id
        process = self._process
        if process and process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process and process.poll() is None:
            process.kill()
        if active_turn_id:
            self._complete_turn(active_turn_id, status=status, error=reason, session_id=self._thread_id)
            self._active_turn_id = ""

    def _shutdown_impl(self) -> None:
        """Shut down Codex process resources and join helper threads."""
        self._cancel_active_turn("agent runtime shutdown", "aborted")
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3.0)
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
