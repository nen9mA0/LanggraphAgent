from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any

from ..types import AgentNodeConfig, TokenUsageSnapshot
from .base import ManagedAgentRuntime


class ClaudeCodeRuntime(ManagedAgentRuntime):
    """Managed runtime that keeps a Claude Code stream-json session alive across turns."""

    def __init__(self, config: AgentNodeConfig, workspace) -> None:
        """Initialize Claude runtime process and reader thread bookkeeping."""
        super().__init__(config, workspace)
        self._active_process: subprocess.Popen[str] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stdin_lock = threading.RLock()

    def _start_impl(self) -> None:
        """Validate the Claude executable and launch the long-lived stream-json process."""
        executable = self.config.executable_path or "claude"
        if shutil.which(executable) is None and not Path(executable).exists():
            raise FileNotFoundError(f"claude executable not found: {executable}")
        self._launch_process()

    def _build_args(self) -> list[str]:
        """Build the Claude CLI arguments for the current long-lived session."""
        args = [
            self.config.executable_path or "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--input-format",
            "stream-json",
            "--verbose",
            "--strict-mcp-config",
            "--permission-mode",
            "bypassPermissions",
        ]
        if self.config.model:
            args.extend(["--model", self.config.model])
        if self.config.max_turns:
            args.extend(["--max-turns", str(self.config.max_turns)])
        if self.config.system_prompt:
            args.extend(["--append-system-prompt", self.config.system_prompt])
        if self.session_id:
            args.extend(["--resume", self.session_id])
        args.extend(self.config.cli_args)
        return args

    def _launch_process(self) -> None:
        """Start the Claude process if it is not already running."""
        process = self._active_process
        if process is not None and process.poll() is None:
            return

        self._stderr_tail.clear()
        process = subprocess.Popen(
            self._build_args(),
            cwd=str(self.config.normalized_working_directory()),
            env={**os.environ, **self.config.env},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._active_process = process
        self._stdout_thread = threading.Thread(target=self._stdout_loop, args=(process,), daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, args=(process,), daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _send_input_impl(self, prompt: str, turn_id: str) -> None:
        """Send a single user turn into the running Claude stream-json session."""
        self._launch_process()
        process = self._active_process
        if process is None or process.stdin is None:
            raise RuntimeError("claude process stdin unavailable")

        payload = {
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
        }
        with self._stdin_lock:
            process.stdin.write(json.dumps(payload, ensure_ascii=True))
            process.stdin.write("\n")
            process.stdin.flush()

    def _stdout_loop(self, process: subprocess.Popen[str]) -> None:
        """Read Claude stdout and map stream-json events into runtime state."""
        if process.stdout is None:
            return
        try:
            for line in process.stdout:
                text = line.strip()
                if not text:
                    continue
                self._handle_message(process, json.loads(text))
        finally:
            if process.stdout is not None:
                process.stdout.close()
            self._mark_process_exit(process)

    def _stderr_loop(self, process: subprocess.Popen[str]) -> None:
        """Read Claude stderr and keep only a bounded diagnostic tail."""
        if process.stderr is None:
            return
        try:
            for line in process.stderr:
                text = line.rstrip()
                if text:
                    self._stderr_tail.append(text)
        finally:
            if process.stderr is not None:
                process.stderr.close()

    def _handle_message(self, process: subprocess.Popen[str], message: dict[str, Any]) -> None:
        """Translate one Claude stream-json message into runtime events and turn state."""
        with self._lock:
            active_turn_id = self._current_turn.result.turn_id if self._current_turn is not None else ""

        message_type = str(message.get("type", ""))
        if message_type == "system":
            session_id = str(message.get("session_id", "") or "")
            self._set_session_id(session_id)
            if active_turn_id:
                self._record_event(active_turn_id, "status", content="running")
            return

        if not active_turn_id:
            return

        if message_type == "assistant":
            assistant_message = message.get("message", {})
            if not isinstance(assistant_message, dict):
                return

            usage = assistant_message.get("usage") or {}
            if isinstance(usage, dict):
                self._merge_usage(
                    active_turn_id,
                    TokenUsageSnapshot(
                        input_tokens=int(usage.get("input_tokens", 0) or 0),
                        output_tokens=int(usage.get("output_tokens", 0) or 0),
                        cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                        cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                        context_window_tokens=self.config.context_window_tokens,
                    ),
                )

            for block in assistant_message.get("content", []):
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    self._record_event(active_turn_id, "text", content=str(block.get("text", "") or ""))
                elif block_type == "thinking":
                    self._record_event(active_turn_id, "thinking", content=str(block.get("text", "") or ""))
                elif block_type == "tool_use":
                    payload = block.get("input", {})
                    self._record_event(
                        active_turn_id,
                        "tool_use",
                        tool_name=str(block.get("name", "") or ""),
                        call_id=str(block.get("id", "") or ""),
                        payload=dict(payload) if isinstance(payload, dict) else {},
                    )
            return

        if message_type == "user":
            user_message = message.get("message", {})
            if not isinstance(user_message, dict):
                return

            for block in user_message.get("content", []):
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                content = block.get("content", "")
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=True)
                self._record_event(
                    active_turn_id,
                    "tool_result",
                    call_id=str(block.get("tool_use_id", "") or ""),
                    content=content,
                )
            return

        if message_type == "log":
            log_entry = message.get("log", {})
            if isinstance(log_entry, dict):
                self._record_event(active_turn_id, "log", content=str(log_entry.get("message", "") or ""))
            return

        if message_type == "result":
            session_id = str(message.get("session_id", "") or "")
            if session_id:
                self._set_session_id(session_id)
            final_output = str(message.get("result", "") or self.get_output_text())
            final_status = "failed" if bool(message.get("is_error")) else "completed"
            final_error = final_output if final_status == "failed" else ""
            self._complete_turn(
                active_turn_id,
                status=final_status,
                final_output=final_output,
                error=final_error,
                session_id=session_id or self.session_id,
            )

    def _mark_process_exit(self, process: subprocess.Popen[str]) -> None:
        """Fail any active turn when the underlying Claude process exits unexpectedly."""
        try:
            exit_code = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            exit_code = process.poll()

        with self._lock:
            is_current_process = process is self._active_process
            active_turn_id = self._current_turn.result.turn_id if self._current_turn is not None else ""

        if is_current_process:
            self._active_process = None

        if not active_turn_id:
            return

        error = "\n".join(self._stderr_tail) or f"claude process exited with code {exit_code}"
        self._complete_turn(
            active_turn_id,
            status="failed",
            error=error,
            final_output=self.get_output_text(),
            session_id=self.session_id,
        )

    def _cancel_active_turn(self, reason: str, status: str) -> None:
        """Terminate the running Claude process and complete the active turn."""
        process = self._active_process
        turn_id = None
        with self._lock:
            if self._current_turn is not None:
                turn_id = self._current_turn.result.turn_id

        if process and process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                pass
        if process and process.stdout is not None:
            process.stdout.close()
        if process and process.stderr is not None:
            process.stderr.close()
        if turn_id:
            self._complete_turn(turn_id, status=status, error=reason, session_id=self.session_id)

    def _shutdown_impl(self) -> None:
        """Shut down the Claude process and join background reader threads."""
        self._cancel_active_turn("agent runtime shutdown", "aborted")
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
        self._active_process = None
