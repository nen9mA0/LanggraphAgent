from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any

from ..types import AgentNodeConfig
from .codex import CodexRuntime


class CodexSDKRuntime(CodexRuntime):
    """Managed runtime that talks to Codex through the Python SDK bridge worker."""

    def __init__(self, config: AgentNodeConfig, workspace) -> None:
        super().__init__(config, workspace)
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._stdin_lock = threading.RLock()
        self._ready = threading.Event()
        self._startup_error = ""

    def _start_impl(self) -> None:
        """Validate the configured Python executable and launch the SDK worker."""
        python_executable = self._python_executable()
        if shutil.which(python_executable) is None and not Path(python_executable).exists():
            raise FileNotFoundError(
                f"python executable for codex_sdk runtime not found: {python_executable}. "
                "Set AgentNodeConfig.runtime_options['python_executable'] to the interpreter that has openai-codex installed."
            )
        self._launch_process()
        if not self._ready.wait(self.config.startup_timeout_seconds):
            self._cancel_active_turn("codex sdk worker startup timed out", "failed")
            raise TimeoutError("codex sdk worker startup timed out")
        if self._startup_error:
            message = self._startup_error
            self._startup_error = ""
            raise RuntimeError(message)

    def _python_executable(self) -> str:
        """Return the Python interpreter path used to host the Codex SDK."""
        return str(self.config.runtime_options.get("python_executable") or self.config.executable_path or "python")

    def _sdk_module(self) -> str:
        """Return the Codex SDK import module name."""
        return str(self.config.runtime_options.get("sdk_module") or "openai_codex")

    def _worker_config_payload(self) -> str:
        """Build the JSON configuration payload passed to the SDK bridge worker."""
        payload = {
            "working_directory": str(self.config.normalized_working_directory()),
            "system_prompt": self.config.system_prompt,
            "model": self.config.model,
            "session_id": self.session_id or None,
            "client_config": dict(self.config.runtime_options.get("client_config") or {}),
            "thread_config": self._thread_config(),
            "turn_kwargs": self._turn_kwargs(),
            "sandbox": self.config.runtime_options.get("sandbox"),
            "approval_mode": self.config.runtime_options.get("approval_mode"),
            "thread_kwargs": dict(self.config.runtime_options.get("thread_kwargs") or {}),
        }
        return json.dumps(payload, ensure_ascii=True)

    def _worker_script_path(self) -> str:
        """Return the absolute path to the local Codex SDK bridge worker script."""
        return str(Path(__file__).with_name("codex_sdk_worker.py").resolve())

    def _thread_config(self) -> dict[str, Any]:
        """Build Codex thread-level config overrides from reusable provider config."""
        config = dict(self.config.runtime_options.get("thread_config") or {})

        reused_base_url = self.config.runtime_options.get("reused_base_url")
        if reused_base_url:
            config.setdefault("base_url", str(reused_base_url))

        reused_skills = self.config.runtime_options.get("reused_skills")
        if isinstance(reused_skills, list) and reused_skills:
            config.setdefault("skills", {"config": [str(item) for item in reused_skills]})

        reused_mcp = self.config.runtime_options.get("reused_mcp")
        if isinstance(reused_mcp, dict) and reused_mcp:
            config.setdefault("mcp_servers", dict(reused_mcp))

        reused_reasoning_effort = self.config.runtime_options.get("reused_model_reasoning_effort")
        if reused_reasoning_effort:
            config.setdefault("model_reasoning_effort", str(reused_reasoning_effort))
        return config

    def _turn_kwargs(self) -> dict[str, Any]:
        """Build per-turn kwargs for the SDK worker."""
        kwargs = dict(self.config.runtime_options.get("turn_kwargs") or {})
        reused_reasoning_effort = self.config.runtime_options.get("reused_model_reasoning_effort")
        if reused_reasoning_effort:
            kwargs.setdefault("effort", str(reused_reasoning_effort))
        return kwargs

    def _launch_process(self) -> None:
        """Start the bridge worker if it is not already running."""
        process = self._process
        if process is not None and process.poll() is None:
            return

        self._stderr_tail.clear()
        self._ready.clear()
        self._startup_error = ""
        process = subprocess.Popen(
            [
                self._python_executable(),
                self._worker_script_path(),
                "--module",
                self._sdk_module(),
                "--config",
                self._worker_config_payload(),
            ],
            cwd=str(self.config.normalized_working_directory()),
            env=self._launch_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._process = process
        self._stdout_thread = threading.Thread(target=self._stdout_loop, args=(process,), daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, args=(process,), daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _send_input_impl(self, prompt: str, turn_id: str) -> None:
        """Send one turn request to the SDK bridge worker."""
        self._launch_process()
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("codex sdk worker stdin unavailable")
        self._active_turn_id = turn_id
        self._active_remote_turn_id = ""
        self._item_text_buffers.clear()
        payload = {"command": "turn", "turn_id": turn_id, "prompt": prompt}
        with self._stdin_lock:
            process.stdin.write(json.dumps(payload, ensure_ascii=True))
            process.stdin.write("\n")
            process.stdin.flush()

    def _stdout_loop(self, process: subprocess.Popen[str]) -> None:
        """Read worker stdout and translate it into runtime events."""
        if process.stdout is None:
            return
        try:
            while True:
                try:
                    line = process.stdout.readline()
                except ValueError:
                    break
                if line == "":
                    break
                text = line.strip()
                if not text:
                    continue
                self._handle_message(process, json.loads(text))
        finally:
            if process.stdout is not None:
                process.stdout.close()
            self._mark_process_exit(process)

    def _stderr_loop(self, process: subprocess.Popen[str]) -> None:
        """Capture a bounded stderr tail from the SDK bridge worker."""
        if process.stderr is None:
            return
        try:
            while True:
                try:
                    line = process.stderr.readline()
                except ValueError:
                    break
                if line == "":
                    break
                text = line.rstrip()
                if text:
                    self._stderr_tail.append(text)
        finally:
            if process.stderr is not None:
                process.stderr.close()

    def _handle_message(self, process: subprocess.Popen[str], message: dict[str, Any]) -> None:
        """Map one worker message into runtime state transitions."""
        message_type = str(message.get("type", "") or "")
        if message_type == "ready":
            session_id = str(message.get("session_id", "") or "")
            if session_id:
                self._thread_id = session_id
                self._set_session_id(session_id)
            self._ready.set()
            return
        if message_type == "error" and not self._ready.is_set():
            self._startup_error = str(message.get("error", "") or "codex sdk worker failed to start")
            self._ready.set()
            return

        session_id = str(message.get("session_id", "") or "")
        if session_id:
            self._thread_id = session_id
            self._set_session_id(session_id)

        with self._lock:
            active_turn_id = self._current_turn.result.turn_id if self._current_turn is not None else ""

        if message_type == "event":
            self._handle_worker_event(
                method=str(message.get("method", "") or ""),
                params=message.get("payload") if isinstance(message.get("payload"), dict) else {},
            )
            return

        if not active_turn_id:
            return

        if message_type == "stream_closed":
            if not bool(message.get("completed")) and self._active_turn_id:
                final_status = "aborted" if bool(message.get("interrupted")) else "failed"
                final_error = "codex sdk turn interrupted" if final_status == "aborted" else "codex sdk stream closed unexpectedly"
                self._complete_turn(
                    active_turn_id,
                    status=final_status,
                    error=final_error,
                    final_output=self.get_output_text(),
                    session_id=self._thread_id,
                )
                self._active_turn_id = ""
                self._active_remote_turn_id = ""
                self._item_text_buffers.clear()
            return

        if message_type == "error":
            error = str(message.get("error", "") or "codex sdk worker error")
            self._record_event(active_turn_id, "error", content=error, payload=dict(message))
            if self._active_turn_id:
                self._complete_turn(
                    active_turn_id,
                    status="failed",
                    error=error,
                    final_output=self.get_output_text(),
                    session_id=self._thread_id,
                )
                self._active_turn_id = ""
                self._active_remote_turn_id = ""
                self._item_text_buffers.clear()

    def _handle_worker_event(self, *, method: str, params: dict[str, Any]) -> None:
        """Route SDK stream notifications through the existing Codex event handlers."""
        if method == "turn/started":
            turn = params.get("turn", {}) if isinstance(params, dict) else {}
            remote_turn_id = str((turn or {}).get("id", "") or "")
            if remote_turn_id:
                self._active_remote_turn_id = remote_turn_id
            self._record_event(self._active_turn_id, "status", content="running")
            return
        if method in {"turn/updated", "turn/stream", "turn/diff/updated", "turn/plan/updated"}:
            self._handle_turn_update(params)
            return
        if method == "turn/completed":
            self._handle_turn_completed(params)
            return
        if method == "turn/failed":
            self._handle_turn_failed(params)
            return
        if method == "thread/tokenUsage/updated":
            self._handle_thread_token_usage_updated(params)
            return
        if method == "warning":
            self._handle_warning_notification(params)
            return
        if method == "error":
            self._handle_error_notification(params)
            return
        if method in {"item/started", "item/updated", "item/completed"}:
            self._handle_item_notification(method, params)
            return
        if method in {
            "item/agentMessage/delta",
            "item/reasoning/textDelta",
            "item/commandExecution/outputDelta",
            "item/fileChange/outputDelta",
            "item/commandExecution/terminalInteraction",
        }:
            self._handle_item_delta_notification(method, params)
            return
        if self._active_turn_id:
            self._record_event(
                self._active_turn_id,
                "log",
                content=f"unhandled Codex SDK notification: {method}",
                payload=params,
            )

    def _mark_process_exit(self, process: subprocess.Popen[str]) -> None:
        """Fail startup or the active turn when the bridge worker exits unexpectedly."""
        try:
            exit_code = process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            exit_code = process.poll()

        with self._lock:
            is_current_process = process is self._process
            active_turn_id = self._current_turn.result.turn_id if self._current_turn is not None else ""

        if is_current_process:
            self._process = None
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()

        error = "\n".join(self._stderr_tail) or f"codex sdk worker exited with code {exit_code}"
        if not self._ready.is_set():
            self._startup_error = error
            self._ready.set()
            return
        if not active_turn_id:
            return
        self._complete_turn(
            active_turn_id,
            status="failed",
            error=error,
            final_output=self.get_output_text(),
            session_id=self._thread_id or self.session_id,
        )
        self._active_turn_id = ""
        self._active_remote_turn_id = ""
        self._item_text_buffers.clear()

    def _cancel_active_turn(self, reason: str, status: str) -> None:
        """Interrupt the worker turn and optionally terminate the worker process."""
        process = self._process
        turn_id = None
        with self._lock:
            if self._current_turn is not None:
                turn_id = self._current_turn.result.turn_id

        if process and process.stdin is not None and not process.stdin.closed:
            payload = {"command": "interrupt"}
            try:
                with self._stdin_lock:
                    process.stdin.write(json.dumps(payload, ensure_ascii=True))
                    process.stdin.write("\n")
                    process.stdin.flush()
            except Exception:
                pass
        if status != "aborted" and process and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                pass
        if turn_id:
            self._complete_turn(
                turn_id,
                status=status,
                error=reason,
                final_output=self.get_output_text(),
                session_id=self._thread_id or self.session_id,
            )
            self._active_turn_id = ""
            self._active_remote_turn_id = ""
            self._item_text_buffers.clear()

    def _shutdown_impl(self) -> None:
        """Shut down the bridge worker and join helper threads."""
        self._cancel_active_turn("agent runtime shutdown", "aborted")
        process = self._process
        if process and process.stdin is not None and not process.stdin.closed:
            try:
                with self._stdin_lock:
                    process.stdin.write(json.dumps({"command": "shutdown"}, ensure_ascii=True))
                    process.stdin.write("\n")
                    process.stdin.flush()
            except Exception:
                pass
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
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
        self._process = None
