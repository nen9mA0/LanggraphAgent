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
    """Managed runtime that executes Claude Code in streaming JSON mode."""

    def __init__(self, config: AgentNodeConfig, workspace) -> None:
        """Initialize Claude runtime process bookkeeping."""
        super().__init__(config, workspace)
        self._active_process: subprocess.Popen[str] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._worker: threading.Thread | None = None

    def _start_impl(self) -> None:
        """Validate that the Claude executable is available."""
        executable = self.config.executable_path or "claude"
        if shutil.which(executable) is None and not Path(executable).exists():
            raise FileNotFoundError(f"claude executable not found: {executable}")

    def _build_args(self) -> list[str]:
        """Build the Claude CLI arguments for the next turn."""
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

    def _send_input_impl(self, prompt: str, turn_id: str) -> None:
        """Launch a Claude process for the turn and stream results asynchronously."""
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
        self._worker = threading.Thread(target=self._run_turn_worker, args=(process, turn_id, prompt), daemon=True)
        self._worker.start()

    def _run_turn_worker(self, process: subprocess.Popen[str], turn_id: str, prompt: str) -> None:
        """Drive one Claude turn from stdin write through stdout event parsing."""
        stderr_thread = threading.Thread(target=self._drain_stderr, args=(process,), daemon=True)
        stderr_thread.start()

        try:
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("claude process stdio unavailable")

            payload = {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
            }
            process.stdin.write(json.dumps(payload, ensure_ascii=True))
            process.stdin.write("\n")
            process.stdin.flush()
            process.stdin.close()

            final_output = ""
            final_status = "completed"
            final_error = ""
            latest_session_id = self.session_id

            for line in process.stdout:
                text = line.strip()
                if not text:
                    continue
                message = json.loads(text)
                message_type = message.get("type")
                if message_type == "system":
                    latest_session_id = message.get("session_id", latest_session_id)
                    self._set_session_id(latest_session_id)
                    self._record_event(turn_id, "status", content="running")
                elif message_type == "assistant":
                    assistant_message = message.get("message", {})
                    usage = assistant_message.get("usage") or {}
                    self._merge_usage(
                        turn_id,
                        TokenUsageSnapshot(
                            input_tokens=int(usage.get("input_tokens", 0) or 0),
                            output_tokens=int(usage.get("output_tokens", 0) or 0),
                            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                            cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                            context_window_tokens=self.config.context_window_tokens,
                        ),
                    )
                    for block in assistant_message.get("content", []):
                        block_type = block.get("type")
                        if block_type == "text":
                            self._record_event(turn_id, "text", content=block.get("text", ""))
                        elif block_type == "thinking":
                            self._record_event(turn_id, "thinking", content=block.get("text", ""))
                        elif block_type == "tool_use":
                            self._record_event(
                                turn_id,
                                "tool_use",
                                tool_name=block.get("name", ""),
                                call_id=block.get("id", ""),
                                payload=dict(block.get("input", {}) or {}),
                            )
                elif message_type == "user":
                    user_message = message.get("message", {})
                    for block in user_message.get("content", []):
                        if block.get("type") == "tool_result":
                            content = block.get("content", "")
                            if not isinstance(content, str):
                                content = json.dumps(content, ensure_ascii=True)
                            self._record_event(
                                turn_id,
                                "tool_result",
                                call_id=block.get("tool_use_id", ""),
                                content=content,
                            )
                elif message_type == "log":
                    log_entry = message.get("log", {})
                    self._record_event(turn_id, "log", content=log_entry.get("message", ""))
                elif message_type == "result":
                    latest_session_id = message.get("session_id", latest_session_id)
                    self._set_session_id(latest_session_id)
                    final_output = message.get("result", final_output)
                    if message.get("is_error"):
                        final_status = "failed"
                        final_error = final_output or "claude returned an error result"

            exit_code = process.wait(timeout=self.config.turn_timeout_seconds)
            stderr_thread.join(timeout=1.0)
            if exit_code != 0 and final_status == "completed":
                final_status = "failed"
                final_error = "\n".join(self._stderr_tail) or f"claude exited with code {exit_code}"
            self._complete_turn(
                turn_id,
                status=final_status,
                final_output=final_output or self.get_output_text(),
                error=final_error,
                session_id=latest_session_id,
            )
        except Exception as exc:
            self._complete_turn(turn_id, status="failed", error=str(exc), session_id=self.session_id)
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            self._active_process = None

    def _drain_stderr(self, process: subprocess.Popen[str]) -> None:
        """Capture a bounded tail of Claude stderr output for diagnostics."""
        if process.stderr is None:
            return
        for line in process.stderr:
            text = line.rstrip()
            if text:
                self._stderr_tail.append(text)

    def _cancel_active_turn(self, reason: str, status: str) -> None:
        """Terminate the in-flight Claude process and finalize the turn."""
        process = self._active_process
        turn_id = None
        with self._lock:
            if self._current_turn is not None:
                turn_id = self._current_turn.result.turn_id
        if process and process.poll() is None:
            process.kill()
        if turn_id:
            self._complete_turn(turn_id, status=status, error=reason, session_id=self.session_id)

    def _shutdown_impl(self) -> None:
        """Shut down any running Claude turn and join the worker thread."""
        self._cancel_active_turn("agent runtime shutdown", "aborted")
        if self._worker is not None:
            self._worker.join(timeout=1.0)
