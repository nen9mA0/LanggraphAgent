from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import threading
from enum import Enum
from pathlib import Path
from typing import Any


_PRINT_LOCK = threading.Lock()


def _emit(payload: dict[str, Any]) -> None:
    """Write one worker event to stdout without interleaving lines."""
    with _PRINT_LOCK:
        print(json.dumps(payload, ensure_ascii=True), flush=True)


def _to_dict(value: Any) -> Any:
    """Convert SDK objects into JSON-serializable primitive structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_dict(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _to_dict(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _to_dict(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {str(key): _to_dict(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


def _extract_thread_id(thread: Any) -> str:
    """Best-effort extraction of a Codex thread identifier."""
    for attr in ("id", "thread_id", "threadId"):
        value = getattr(thread, attr, "")
        if value:
            return str(value)
    return ""


def _coerce_enum_value(enum_cls: Any, raw_value: Any) -> Any:
    """Map a string into an SDK enum member when the enum is available."""
    if enum_cls is None or raw_value in {None, ""}:
        return None
    if isinstance(raw_value, enum_cls):
        return raw_value
    text = str(raw_value)
    candidates = [text, text.upper(), text.lower()]
    snake_upper = text.replace("-", "_").replace(" ", "_").upper()
    snake_lower = text.replace("-", "_").replace(" ", "_").lower()
    candidates.extend([snake_upper, snake_lower])
    for candidate in candidates:
        member = getattr(enum_cls, candidate, None)
        if member is not None:
            return member
    try:
        return enum_cls(text)
    except Exception:
        return raw_value


def _build_client(module: Any, client_config: dict[str, Any]) -> Any:
    """Instantiate the Codex SDK client."""
    codex_cls = getattr(module, "Codex", None)
    if codex_cls is None:
        raise RuntimeError(f"module '{module.__name__}' does not export Codex")

    if not client_config:
        client = codex_cls()
    else:
        config_cls = getattr(module, "CodexConfig", None)
        if config_cls is None:
            raise RuntimeError(
                f"module '{module.__name__}' does not export CodexConfig, "
                "so worker client_config cannot be applied"
            )
        client = codex_cls(config=config_cls(**client_config))

    if hasattr(client, "__enter__"):
        client = client.__enter__()
    return client


def _close_client(client: Any) -> None:
    """Close the Codex SDK client when it exposes a context-manager exit."""
    if hasattr(client, "__exit__"):
        client.__exit__(None, None, None)
    elif hasattr(client, "close"):
        client.close()


def _build_thread_kwargs(module: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Translate worker config payload into thread start/resume kwargs."""
    kwargs = dict(payload.get("thread_kwargs") or {})
    working_directory = payload.get("working_directory")
    if working_directory:
        kwargs.setdefault("cwd", str(Path(working_directory).resolve()))
    system_prompt = payload.get("system_prompt")
    if system_prompt:
        kwargs.setdefault("developer_instructions", str(system_prompt))
    model = payload.get("model")
    if model:
        kwargs.setdefault("model", str(model))
    thread_config = payload.get("thread_config")
    if isinstance(thread_config, dict) and thread_config:
        kwargs.setdefault("config", dict(thread_config))
    sandbox_value = _coerce_enum_value(getattr(module, "Sandbox", None), payload.get("sandbox"))
    if sandbox_value is not None:
        kwargs.setdefault("sandbox", sandbox_value)
    approval_mode = _coerce_enum_value(getattr(module, "ApprovalMode", None), payload.get("approval_mode"))
    if approval_mode is not None:
        kwargs.setdefault("approval_mode", approval_mode)
    return kwargs


def _build_turn_kwargs(module: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Translate worker config payload into per-turn kwargs."""
    kwargs = dict(payload.get("turn_kwargs") or {})
    sandbox_value = _coerce_enum_value(getattr(module, "Sandbox", None), payload.get("sandbox"))
    if sandbox_value is not None:
        kwargs.setdefault("sandbox", sandbox_value)
    approval_mode = _coerce_enum_value(getattr(module, "ApprovalMode", None), payload.get("approval_mode"))
    if approval_mode is not None:
        kwargs.setdefault("approval_mode", approval_mode)
    return kwargs


class _TurnRunner:
    """Background stream runner so stdin can continue handling interrupts."""

    def __init__(self, *, thread: Any, turn_id: str, handle: Any) -> None:
        self.thread = thread
        self.turn_id = turn_id
        self.handle = handle
        self.interrupt_requested = False
        self.completed = False
        self.worker = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.worker.start()

    def interrupt(self) -> None:
        self.interrupt_requested = True
        interrupt = getattr(self.handle, "interrupt", None)
        if interrupt is None:
            return
        interrupt()

    def join(self, timeout: float | None = None) -> None:
        self.worker.join(timeout=timeout)

    def _run(self) -> None:
        try:
            stream = getattr(self.handle, "stream", None)
            if stream is None:
                raise RuntimeError("TurnHandle.stream is unavailable")
            for notification in stream():
                method = str(getattr(notification, "method", "") or "")
                payload = _to_dict(getattr(notification, "payload", None))
                if method == "turn/completed":
                    self.completed = True
                _emit(
                    {
                        "type": "event",
                        "turn_id": self.turn_id,
                        "session_id": _extract_thread_id(self.thread),
                        "method": method,
                        "payload": payload if isinstance(payload, dict) else {},
                    }
                )
        except Exception as exc:
            _emit(
                {
                    "type": "error",
                    "turn_id": self.turn_id,
                    "session_id": _extract_thread_id(self.thread),
                    "error": str(exc),
                }
            )
            return

        _emit(
            {
                "type": "stream_closed",
                "turn_id": self.turn_id,
                "session_id": _extract_thread_id(self.thread),
                "interrupted": self.interrupt_requested,
                "completed": self.completed,
            }
        )


def _open_thread(module: Any, client: Any, payload: dict[str, Any]) -> Any:
    """Create or resume one Codex thread."""
    thread_start = getattr(client, "thread_start", None)
    thread_resume = getattr(client, "thread_resume", None)
    if thread_start is None:
        raise RuntimeError("Codex.thread_start is unavailable")

    thread_kwargs = _build_thread_kwargs(module, payload)
    session_id = str(payload.get("session_id", "") or "")
    if session_id and thread_resume is not None:
        try:
            return thread_resume(session_id, **thread_kwargs)
        except Exception:
            pass
    return thread_start(**thread_kwargs)


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for the Codex SDK bridge worker."""
    parser = argparse.ArgumentParser(description="workflow_agents Codex SDK bridge worker")
    parser.add_argument("--module", default="openai_codex", help="Codex SDK import module name.")
    parser.add_argument("--config", required=True, help="JSON-encoded worker configuration.")
    return parser


def main() -> int:
    """Run the worker entrypoint."""
    parser = _build_parser()
    args = parser.parse_args()
    payload = json.loads(args.config)

    os.chdir(str(Path(payload["working_directory"]).resolve()))
    module = importlib.import_module(args.module)
    client = _build_client(module, dict(payload.get("client_config") or {}))

    current_runner: _TurnRunner | None = None
    try:
        thread = _open_thread(module, client, payload)
        _emit({"type": "ready", "session_id": _extract_thread_id(thread)})
        turn_kwargs = _build_turn_kwargs(module, payload)

        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            message = json.loads(line)
            command = str(message.get("command", ""))

            if command == "shutdown":
                break
            if command == "interrupt":
                if current_runner is not None:
                    current_runner.interrupt()
                    _emit(
                        {
                            "type": "interrupt_sent",
                            "turn_id": current_runner.turn_id,
                            "session_id": _extract_thread_id(thread),
                        }
                    )
                continue
            if command != "turn":
                _emit({"type": "error", "error": f"unsupported command: {command}"})
                continue
            if current_runner is not None and current_runner.worker.is_alive():
                _emit({"type": "error", "error": "codex sdk worker already has an active turn"})
                continue

            prompt = str(message.get("prompt", "") or "")
            turn_id = str(message.get("turn_id", "") or "")
            turn_method = getattr(thread, "turn", None)
            if turn_method is None:
                raise RuntimeError("Thread.turn is unavailable")
            handle = turn_method(prompt, **turn_kwargs)
            current_runner = _TurnRunner(thread=thread, turn_id=turn_id, handle=handle)
            current_runner.start()
    finally:
        if current_runner is not None:
            current_runner.interrupt()
            current_runner.join(timeout=3.0)
        _close_client(client)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        _emit({"type": "error", "error": str(exc)})
        raise
