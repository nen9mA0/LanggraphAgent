from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


def _to_dict(value: Any) -> Any:
    """Convert SDK objects into JSON-serializable primitive structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
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


def _extract_session_id(client: Any) -> str:
    """Best-effort extraction of the current Claude SDK session identifier."""
    for attr in ("session_id", "sessionId", "_session_id"):
        value = getattr(client, attr, "")
        if value:
            return str(value)
    return ""


def _extract_content_text(block: dict[str, Any]) -> str:
    """Extract displayable text from a content block payload."""
    text = block.get("text")
    if isinstance(text, str):
        return text
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                piece = item.get("text")
                if isinstance(piece, str):
                    parts.append(piece)
        return "".join(parts)
    return ""


def _usage_from_message(message: Any) -> dict[str, Any]:
    """Read common usage fields from a Claude SDK message object."""
    usage = getattr(message, "usage", None)
    if usage is None and isinstance(message, dict):
        usage = message.get("usage")
    usage_dict = _to_dict(usage) if usage is not None else {}
    if not isinstance(usage_dict, dict):
        usage_dict = {}
    return usage_dict


async def _open_client(module_name: str, options: dict[str, Any]) -> Any:
    """Import the SDK module and open a ClaudeSDKClient instance."""
    module = importlib.import_module(module_name)
    client_cls = getattr(module, "ClaudeSDKClient", None)
    options_cls = getattr(module, "ClaudeAgentOptions", None)
    if client_cls is None:
        raise RuntimeError(f"module '{module_name}' does not export ClaudeSDKClient")
    client_options = options_cls(**options) if options_cls is not None else options
    client = client_cls(options=client_options)
    if hasattr(client, "__aenter__"):
        client = await client.__aenter__()
    elif hasattr(client, "connect"):
        await client.connect()
    return client


async def _close_client(client: Any) -> None:
    """Close the SDK client if it exposes async context-manager shutdown."""
    if hasattr(client, "__aexit__"):
        await client.__aexit__(None, None, None)
    elif hasattr(client, "disconnect"):
        result = client.disconnect()
        if asyncio.iscoroutine(result):
            await result


async def _send_query(client: Any, prompt: str) -> None:
    """Dispatch one user query to Claude SDK."""
    query = getattr(client, "query", None)
    if query is None:
        raise RuntimeError("ClaudeSDKClient.query is unavailable")
    result = query(prompt)
    if asyncio.iscoroutine(result):
        await result


def _receive_response(client: Any) -> Any:
    """Return the SDK async iterator for the current response stream."""
    receive = getattr(client, "receive_response", None)
    if receive is None:
        raise RuntimeError("ClaudeSDKClient.receive_response is unavailable")
    return receive()


async def _interrupt(client: Any) -> None:
    """Interrupt the current Claude SDK turn when supported."""
    interrupt = getattr(client, "interrupt", None)
    if interrupt is None:
        return
    result = interrupt()
    if asyncio.iscoroutine(result):
        await result


async def _run_loop(module_name: str, options: dict[str, Any]) -> int:
    """Run the stdin/stdout bridge loop that proxies Claude SDK events."""
    client = await _open_client(module_name, options)
    try:
        print(
            json.dumps(
                {
                    "type": "ready",
                    "session_id": _extract_session_id(client),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        loop = asyncio.get_running_loop()
        pending_turn = False
        while True:
            raw = await loop.run_in_executor(None, sys.stdin.readline)
            if raw == "":
                break
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            command = str(payload.get("command", ""))

            if command == "shutdown":
                break
            if command == "interrupt":
                await _interrupt(client)
                pending_turn = False
                print(json.dumps({"type": "interrupted"}, ensure_ascii=True), flush=True)
                continue
            if command != "turn":
                print(
                    json.dumps({"type": "error", "error": f"unsupported command: {command}"}, ensure_ascii=True),
                    flush=True,
                )
                continue

            turn_id = str(payload.get("turn_id", ""))
            prompt = str(payload.get("prompt", ""))
            pending_turn = True
            await _send_query(client, prompt)
            session_id = _extract_session_id(client)
            if session_id:
                print(json.dumps({"type": "system", "session_id": session_id}, ensure_ascii=True), flush=True)

            async for message in _receive_response(client):
                event_name = type(message).__name__
                message_dict = _to_dict(message)

                if event_name == "AssistantMessage":
                    print(
                        json.dumps(
                            {
                                "type": "assistant",
                                "turn_id": turn_id,
                                "session_id": _extract_session_id(client),
                                "usage": _usage_from_message(message),
                                "message": message_dict,
                            },
                            ensure_ascii=True,
                        ),
                        flush=True,
                    )
                    continue

                if event_name == "UserMessage":
                    print(
                        json.dumps(
                            {
                                "type": "user",
                                "turn_id": turn_id,
                                "session_id": _extract_session_id(client),
                                "message": message_dict,
                            },
                            ensure_ascii=True,
                        ),
                        flush=True,
                    )
                    continue

                if event_name == "SystemMessage":
                    print(
                        json.dumps(
                            {
                                "type": "system",
                                "turn_id": turn_id,
                                "session_id": _extract_session_id(client),
                                "message": message_dict,
                            },
                            ensure_ascii=True,
                        ),
                        flush=True,
                    )
                    continue

                if event_name == "ResultMessage":
                    result_text = ""
                    subtype = ""
                    if isinstance(message_dict, dict):
                        subtype = str(message_dict.get("subtype", "") or "")
                        result_text = str(message_dict.get("result", "") or "")
                    print(
                        json.dumps(
                            {
                                "type": "result",
                                "turn_id": turn_id,
                                "session_id": _extract_session_id(client),
                                "result": result_text,
                                "subtype": subtype,
                                "is_error": subtype == "error_max_turns",
                                "message": message_dict,
                            },
                            ensure_ascii=True,
                        ),
                        flush=True,
                    )
                    pending_turn = False
                    continue

                text = ""
                if isinstance(message_dict, dict):
                    text = _extract_content_text(message_dict)
                print(
                    json.dumps(
                        {
                            "type": "log",
                            "turn_id": turn_id,
                            "session_id": _extract_session_id(client),
                            "event_name": event_name,
                            "text": text,
                            "payload": message_dict,
                        },
                        ensure_ascii=True,
                    ),
                        flush=True,
                    )
                if not pending_turn:
                    break
    finally:
        await _close_client(client)
    return 0


def _build_options(payload: dict[str, Any]) -> dict[str, Any]:
    """Translate worker launch payload into SDK client options."""
    options = dict(payload.get("client_options") or {})
    cwd = payload.get("working_directory")
    if cwd:
        options.setdefault("cwd", str(Path(cwd).resolve()))
    system_prompt = payload.get("system_prompt")
    if system_prompt:
        options.setdefault("system_prompt", system_prompt)
    model = payload.get("model")
    if model:
        options.setdefault("model", model)
    max_turns = payload.get("max_turns")
    if max_turns:
        options.setdefault("max_turns", max_turns)
    cli_path = payload.get("cli_path")
    if cli_path:
        options.setdefault("cli_path", cli_path)
    mcp_config_path = payload.get("mcp_config_path")
    if mcp_config_path:
        options.setdefault("mcp_config", mcp_config_path)
    session_id = payload.get("session_id")
    if session_id:
        options.setdefault("resume", session_id)
    return options


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for the SDK bridge worker."""
    parser = argparse.ArgumentParser(description="workflow_agents Claude SDK bridge worker")
    parser.add_argument("--module", default="claude_agent_sdk", help="Claude SDK import module name.")
    parser.add_argument("--config", required=True, help="JSON-encoded worker configuration.")
    return parser


def main() -> int:
    """Run the worker entrypoint."""
    parser = _build_parser()
    args = parser.parse_args()
    payload = json.loads(args.config)
    env_payload = payload.get("env") or {}
    if isinstance(env_payload, dict):
        for key, value in env_payload.items():
            os.environ[str(key)] = str(value)
    os.chdir(str(Path(payload["working_directory"]).resolve()))
    options = _build_options(payload)
    return asyncio.run(_run_loop(args.module, options))


if __name__ == "__main__":
    raise SystemExit(main())
