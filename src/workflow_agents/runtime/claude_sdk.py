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


class ClaudeSDKRuntime(ManagedAgentRuntime):
    """Managed runtime that talks to Claude through a Python SDK bridge worker."""

    def __init__(self, config: AgentNodeConfig, workspace) -> None:
        """Initialize Claude SDK runtime process and worker IO bookkeeping."""
        super().__init__(config, workspace)
        self._process: subprocess.Popen[str] | None = None
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
                f"python executable for claude_sdk runtime not found: {python_executable}. "
                "Set AgentNodeConfig.runtime_options['python_executable'] to the interpreter that has claude-agent-sdk installed."
            )
        self._launch_process()
        if not self._ready.wait(self.config.startup_timeout_seconds):
            self._cancel_active_turn("claude sdk worker startup timed out", "failed")
            raise TimeoutError("claude sdk worker startup timed out")
        if self._startup_error:
            message = self._startup_error
            self._startup_error = ""
            raise RuntimeError(message)

    def _python_executable(self) -> str:
        """Return the Python interpreter path used to host the Claude SDK."""
        return str(self.config.runtime_options.get("python_executable") or self.config.executable_path or "python")

    def _sdk_module(self) -> str:
        """Return the Claude SDK import module name."""
        return str(self.config.runtime_options.get("sdk_module") or "claude_agent_sdk")

    def _worker_config_payload(self) -> str:
        """Build the JSON configuration payload passed to the SDK bridge worker."""
        env_payload = dict(self.config.env)
        if not str(env_payload.get("CLAUDE_CONFIG_DIR", "") or "").strip():
            config_dir = self._prepare_reused_config_dir()
            if config_dir is not None:
                env_payload["CLAUDE_CONFIG_DIR"] = str(config_dir)
        mcp_config_path = self._prepare_reused_mcp_config()
        payload = {
            "working_directory": str(self.config.normalized_working_directory()),
            "system_prompt": self.config.system_prompt,
            "model": self.config.model,
            "max_turns": self.config.max_turns,
            "cli_path": self.config.runtime_options.get("cli_path"),
            "session_id": self.session_id or None,
            "client_options": dict(self.config.runtime_options.get("client_options") or {}),
            "env": env_payload,
            "mcp_config_path": str(mcp_config_path) if mcp_config_path is not None else None,
        }
        return json.dumps(payload, ensure_ascii=True)

    def _worker_script_path(self) -> str:
        """Return the absolute path to the local SDK bridge worker script."""
        return str(Path(__file__).with_name("claude_sdk_worker.py").resolve())

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
            env={**os.environ, **self.config.env},
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
        """Send one turn request to the bridge worker."""
        self._launch_process()
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("claude sdk worker stdin unavailable")
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
        """Capture a bounded stderr tail from the SDK bridge worker."""
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
        """Map one worker message into runtime state transitions."""
        message_type = str(message.get("type", ""))
        if message_type == "ready":
            session_id = str(message.get("session_id", "") or "")
            if session_id:
                self._set_session_id(session_id)
            self._ready.set()
            return
        if message_type == "error" and not self._ready.is_set():
            self._startup_error = str(message.get("error", "") or "claude sdk worker failed to start")
            self._ready.set()
            return

        with self._lock:
            active_turn_id = self._current_turn.result.turn_id if self._current_turn is not None else ""

        if message_type == "system":
            session_id = str(message.get("session_id", "") or "")
            if session_id:
                self._set_session_id(session_id)
            if active_turn_id:
                self._record_event(active_turn_id, "status", content="running")
            return

        if not active_turn_id:
            return

        if message_type == "assistant":
            usage = message.get("usage") or {}
            if isinstance(usage, dict):
                self._replace_usage(
                    active_turn_id,
                    TokenUsageSnapshot(
                        input_tokens=int(usage.get("input_tokens", 0) or 0),
                        output_tokens=int(usage.get("output_tokens", 0) or 0),
                        cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or usage.get("cache_read_tokens", 0) or 0),
                        cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or usage.get("cache_write_tokens", 0) or 0),
                        context_window_tokens=self.config.context_window_tokens,
                    ),
                )
            assistant_message = message.get("message", {}) or {}
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
            user_message = message.get("message", {}) or {}
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
            text = str(message.get("text", "") or "")
            if text:
                self._record_event(active_turn_id, "log", content=text, payload=dict(message.get("payload") or {}))
            return

        if message_type == "result":
            session_id = str(message.get("session_id", "") or "")
            if session_id:
                self._set_session_id(session_id)
            result_text = str(message.get("result", "") or self.get_output_text())
            subtype = str(message.get("subtype", "") or "")
            is_error = bool(message.get("is_error"))
            final_status = "failed" if is_error else "completed"
            final_error = result_text if is_error else ""
            if subtype and not final_error and final_status == "failed":
                final_error = subtype
            self._complete_turn(
                active_turn_id,
                status=final_status,
                final_output=result_text,
                error=final_error,
                session_id=session_id or self.session_id,
            )
            return

        if message_type == "interrupted":
            self._complete_turn(
                active_turn_id,
                status="aborted",
                error="claude sdk turn interrupted",
                final_output=self.get_output_text(),
                session_id=self.session_id,
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

        error = "\n".join(self._stderr_tail) or f"claude sdk worker exited with code {exit_code}"
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
            session_id=self.session_id,
        )

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
            self._complete_turn(turn_id, status=status, error=reason, session_id=self.session_id)

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

    def _prepare_reused_config_dir(self) -> Path | None:
        """Prepare the Claude user-config overlay directory when local reused config exists."""
        config_dir = self.workspace.root / ".claude"
        has_local_settings = config_dir.joinpath("settings.json").exists() or config_dir.joinpath("settings.local.json").exists()
        has_reused_skills = self._sync_reused_skills(config_dir)
        if has_local_settings or has_reused_skills:
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir
        return None

    def _sync_reused_skills(self, config_dir: Path) -> bool:
        """Copy reused skill directories into the Claude config overlay."""
        reused_skills = list(self.config.runtime_options.get("reused_skills") or [])
        if not reused_skills:
            return False

        skills_root = config_dir / "skills"
        copied_any = False
        for item in reused_skills:
            source_dir = self._resolve_reused_skill_directory(str(item))
            if source_dir is None:
                continue
            target_dir = skills_root / source_dir.name
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            copied_any = True
        return copied_any

    def _resolve_reused_skill_directory(self, value: str) -> Path | None:
        """Resolve a reused skill selector into a concrete skill directory."""
        raw = value.strip()
        if not raw:
            return None

        candidates: list[Path] = []
        direct = Path(raw).expanduser()
        candidates.append(direct)
        if not direct.is_absolute():
            candidates.append(self.config.normalized_working_directory() / raw)
            candidates.append(Path.home() / ".claude" / "skills" / raw)

        for candidate in candidates:
            resolved = candidate.resolve(strict=False)
            if resolved.is_file() and resolved.name == "SKILL.md":
                return resolved.parent if resolved.exists() else None
            if resolved.is_dir() and resolved.joinpath("SKILL.md").exists():
                return resolved
        return None

    def _prepare_reused_mcp_config(self) -> Path | None:
        """Materialize the reused Claude MCP payload into a temporary JSON config file."""
        reused_mcp = self.config.runtime_options.get("reused_mcp") or {}
        if not isinstance(reused_mcp, dict) or not reused_mcp:
            return None

        config_path = self.workspace.root / "reused_mcp.json"
        payload = {"mcpServers": reused_mcp}
        config_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        return config_path
