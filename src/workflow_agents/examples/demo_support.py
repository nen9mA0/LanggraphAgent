from __future__ import annotations

import sys
import textwrap
from pathlib import Path


FAKE_CLAUDE_SCRIPT = textwrap.dedent(
    """
    import json
    import sys

    args = sys.argv[1:]
    session_id = "claude-demo-session"
    if "--resume" in args:
        session_id = args[args.index("--resume") + 1]
    payload = json.loads(sys.stdin.readline())
    prompt = payload["message"]["content"][0]["text"]
    events = [
        {"type": "system", "session_id": session_id},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "fake-claude",
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "content": [
                    {"type": "thinking", "text": "drafting"},
                    {"type": "tool_use", "id": "tool-1", "name": "shell", "input": {"command": "echo hidden"}},
                    {"type": "text", "text": "Writer draft complete.\\n"},
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "ok"}],
            },
        },
        {
            "type": "result",
            "session_id": session_id,
            "result": "Writer final answer\\n\\nBased on prompt:\\n" + prompt,
            "is_error": False,
        },
    ]
    for item in events:
        print(json.dumps(item), flush=True)
    """
)


FAKE_CODEX_SCRIPT = textwrap.dedent(
    """
    import json
    import sys

    thread_id = "codex-demo-thread"
    turn_index = 0

    def reply(message):
        print(json.dumps(message), flush=True)

    for raw in sys.stdin:
        payload = json.loads(raw)
        method = payload.get("method")
        if "id" in payload and method == "initialize":
            reply({"jsonrpc": "2.0", "id": payload["id"], "result": {}})
        elif method == "initialized":
            continue
        elif "id" in payload and method == "thread/resume":
            requested = payload["params"]["threadId"]
            thread_id = requested or thread_id
            reply({"jsonrpc": "2.0", "id": payload["id"], "result": {"thread": {"id": thread_id}}})
        elif "id" in payload and method == "thread/start":
            reply({"jsonrpc": "2.0", "id": payload["id"], "result": {"thread": {"id": thread_id}}})
        elif "id" in payload and method == "turn/start":
            turn_index += 1
            prompt = payload["params"]["input"][0]["text"]
            turn_id = f"turn-{turn_index}"
            reply({"jsonrpc": "2.0", "id": payload["id"], "result": {"turn": {"id": turn_id}}})
            reply({"jsonrpc": "2.0", "method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id}}})
            reply({
                "jsonrpc": "2.0",
                "method": "item/started",
                "params": {
                    "threadId": thread_id,
                    "item": {"id": "cmd-1", "type": "commandExecution", "command": "echo hidden"},
                },
            })
            reply({
                "jsonrpc": "2.0",
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "item": {"id": "cmd-1", "type": "commandExecution", "aggregatedOutput": "ok"},
                },
            })
            reply({
                "jsonrpc": "2.0",
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "item": {"id": "msg-1", "type": "agentMessage", "text": "Reviewer final answer\\n\\nReviewed prompt:\\n" + prompt, "phase": "final_answer"},
                },
            })
            reply({
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": thread_id,
                    "turn": {"id": turn_id, "status": "completed", "usage": {"input_tokens": 8, "output_tokens": 16}},
                },
            })
        elif "id" in payload:
            reply({"jsonrpc": "2.0", "id": payload["id"], "result": {}})
    """
)


def create_windows_cmd_wrapper(directory: Path, name: str, script_content: str) -> str:
    script_path = directory / f"{name}.py"
    script_path.write_text(script_content, encoding="utf-8")
    wrapper_path = directory / f"{name}.cmd"
    wrapper_path.write_text(
        f'@echo off\r\n"{sys.executable}" "{script_path}" %*\r\n',
        encoding="utf-8",
    )
    return str(wrapper_path)

