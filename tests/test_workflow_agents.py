from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workflow_agents import AgentNode, AgentNodeConfig, AgentRuntimeRegistry, InterNodeMessage


def create_cmd_wrapper(directory: Path, name: str, script_content: str) -> str:
    script_path = directory / f"{name}.py"
    script_path.write_text(script_content, encoding="utf-8")
    wrapper_path = directory / f"{name}.cmd"
    wrapper_path.write_text(
        f'@echo off\r\n"{sys.executable}" "{script_path}" %*\r\n',
        encoding="utf-8",
    )
    return str(wrapper_path)


FAKE_CLAUDE = """
import json
import sys

args = sys.argv[1:]
session_id = "claude-session-1"
if "--resume" in args:
    session_id = args[args.index("--resume") + 1]
for raw in sys.stdin:
    if not raw.strip():
        continue
    payload = json.loads(raw)
    prompt = payload["message"]["content"][0]["text"]
    events = [
        {"type": "system", "session_id": session_id},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": "fake-claude",
                "usage": {
                    "input_tokens": 4,
                    "output_tokens": 6,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "shell", "input": {"command": "echo hidden"}},
                    {"type": "text", "text": f"stream:{prompt}"},
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
        {"type": "result", "session_id": session_id, "result": f"final:{prompt}", "is_error": False},
    ]
    for item in events:
        print(json.dumps(item), flush=True)
"""

FAKE_CODEX = """
import json
import sys

thread_id = "codex-thread-1"
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
                "item": {"id": "msg-1", "type": "agentMessage", "text": f"final:{prompt}", "phase": "final_answer"},
            },
        })
        reply({
            "jsonrpc": "2.0",
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed", "usage": {"input_tokens": 3, "output_tokens": 7}},
            },
        })
    elif "id" in payload:
        reply({"jsonrpc": "2.0", "id": payload["id"], "result": {}})
"""

FAKE_CLAUDE_SDK = """
import asyncio


class ClaudeAgentOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)


class AssistantMessage:
    def __init__(self, content, usage):
        self.content = content
        self.usage = usage

    def model_dump(self):
        return {"content": self.content, "usage": self.usage}


class UserMessage:
    def __init__(self, content):
        self.content = content

    def model_dump(self):
        return {"content": self.content}


class ResultMessage:
    def __init__(self, result, subtype="success"):
        self.result = result
        self.subtype = subtype

    def model_dump(self):
        return {"result": self.result, "subtype": self.subtype}


class ClaudeSDKClient:
    def __init__(self, options):
        self.options = options
        self.session_id = getattr(options, "resume", "") or "sdk-session-1"
        self._prompt = ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def query(self, prompt):
        self._prompt = prompt

    def receive_response(self):
        prompt = self._prompt

        async def iterator():
            yield AssistantMessage(
                content=[
                    {"type": "thinking", "text": "reasoning"},
                    {"type": "tool_use", "id": "sdk-tool-1", "name": "read_file", "input": {"path": "README.md"}},
                    {"type": "text", "text": f"sdk-stream:{prompt}"},
                ],
                usage={
                    "input_tokens": 5,
                    "output_tokens": 8,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            )
            yield UserMessage(
                content=[{"type": "tool_result", "tool_use_id": "sdk-tool-1", "content": "file-ok"}]
            )
            yield ResultMessage(result=f"sdk-final:{prompt}")

        return iterator()

    async def interrupt(self):
        await asyncio.sleep(0)
"""


class WorkflowAgentsTestCase(unittest.TestCase):
    def test_workspace_names_are_suffixed_on_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            fake_claude = create_cmd_wrapper(Path(temp_dir), "fake_claude_names", FAKE_CLAUDE)

            config_a = AgentNodeConfig(
                name="writer",
                agent_type="claude",
                executable_path=fake_claude,
                working_directory=temp_dir,
                auto_start=False,
            )
            config_b = AgentNodeConfig(
                name="writer",
                agent_type="claude",
                executable_path=fake_claude,
                working_directory=temp_dir,
                auto_start=False,
            )

            runtime_a = registry.get_or_create(config_a)
            runtime_b = registry.get_or_create(config_b)
            self.assertEqual(runtime_a.workspace.root.name, "writer")
            self.assertEqual(runtime_b.workspace.root.name, "writer_1")

    def test_claude_runtime_exposes_usage_completion_and_persists_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_claude = create_cmd_wrapper(Path(temp_dir), "fake_claude", FAKE_CLAUDE)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            config = AgentNodeConfig(
                name="claude_writer",
                agent_type="claude",
                executable_path=fake_claude,
                working_directory=temp_dir,
                context_window_tokens=100,
            )

            runtime = registry.get_or_create(config)
            first = runtime.run_turn("hello")
            self.assertEqual(first.status, "completed")
            self.assertEqual(first.final_output, "final:hello")
            self.assertTrue(runtime.is_output_complete())
            self.assertAlmostEqual(runtime.get_context_usage_ratio() or 0.0, 0.1)
            self.assertEqual(runtime.session_id, "claude-session-1")

            second = runtime.run_turn("world")
            self.assertEqual(second.session_id, "claude-session-1")
            self.assertEqual(second.final_output, "final:world")
            runtime.shutdown()

    def test_claude_sdk_runtime_exposes_usage_completion_and_persists_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sdk_module = Path(temp_dir) / "claude_agent_sdk.py"
            sdk_module.write_text(FAKE_CLAUDE_SDK, encoding="utf-8")
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            config = AgentNodeConfig(
                name="claude_sdk_writer",
                agent_type="claude_sdk",
                executable_path=sys.executable,
                working_directory=temp_dir,
                context_window_tokens=100,
                env={"PYTHONPATH": temp_dir},
                runtime_options={"python_executable": sys.executable},
            )

            runtime = registry.get_or_create(config)
            first = runtime.run_turn("hello sdk")
            self.assertEqual(first.status, "completed")
            self.assertEqual(first.final_output, "sdk-final:hello sdk")
            self.assertTrue(runtime.is_output_complete())
            self.assertAlmostEqual(runtime.get_context_usage_ratio() or 0.0, 0.13)
            self.assertEqual(runtime.session_id, "sdk-session-1")
            event_types = [event.event_type for event in first.events]
            self.assertIn("thinking", event_types)
            self.assertIn("tool_use", event_types)
            self.assertIn("tool_result", event_types)

            second = runtime.run_turn("world sdk")
            self.assertEqual(second.session_id, "sdk-session-1")
            self.assertEqual(second.final_output, "sdk-final:world sdk")
            runtime.shutdown()

    def test_codex_runtime_keeps_thread_and_streams_tool_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_codex = create_cmd_wrapper(Path(temp_dir), "fake_codex", FAKE_CODEX)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            config = AgentNodeConfig(
                name="codex_worker",
                agent_type="codex",
                executable_path=fake_codex,
                working_directory=temp_dir,
                context_window_tokens=100,
            )

            runtime = registry.get_or_create(config)
            first = runtime.run_turn("task one")
            self.assertEqual(first.status, "completed")
            self.assertEqual(first.final_output, "final:task one")
            self.assertEqual(first.session_id, "codex-thread-1")
            self.assertAlmostEqual(runtime.get_context_usage_ratio() or 0.0, 0.1)

            events = runtime.get_output_events()
            event_types = [event.event_type for event in events]
            self.assertIn("tool_use", event_types)
            self.assertIn("tool_result", event_types)

            second = runtime.run_turn("task two")
            self.assertEqual(second.session_id, "codex-thread-1")
            self.assertEqual(second.final_output, "final:task two")
            runtime.shutdown()

    def test_agent_node_only_forwards_final_output_to_other_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_claude = create_cmd_wrapper(Path(temp_dir), "fake_claude_node", FAKE_CLAUDE)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            try:
                node = AgentNode(
                    config=AgentNodeConfig(
                        name="writer",
                        agent_type="claude",
                        executable_path=fake_claude,
                        working_directory=temp_dir,
                        targets=("reviewer",),
                    ),
                    registry=registry,
                )

                state = {
                    "mailboxes": {
                        "writer": [
                            InterNodeMessage(sender="planner", recipient="writer", content="Draft section A").to_dict()
                        ]
                    }
                }
                result = node(state)

                writer_result = result["agent_results"]["writer"]
                forwarded = result["mailboxes"]["reviewer"][0]
                self.assertEqual(forwarded["content"], writer_result["final_output"])
                self.assertIn("Draft section A", writer_result["final_output"])
                self.assertEqual(result["mailboxes"].get("writer"), [])

                workspace = Path(writer_result["workspace"])
                history_lines = workspace.joinpath("history.jsonl").read_text(encoding="utf-8").strip().splitlines()
                self.assertTrue(any('"kind": "event"' in line for line in history_lines))
                self.assertNotIn("echo hidden", forwarded["content"])
            finally:
                registry.shutdown_all()

    def test_langgraph_demo_runs_end_to_end_with_fake_cli(self) -> None:
        try:
            import langgraph  # noqa: F401
            from workflow_agents.examples.langgraph_demo import run_demo
        except ModuleNotFoundError as exc:
            self.skipTest(f"langgraph is not installed in the current interpreter: {exc}")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_demo(
                working_directory=temp_dir,
                topic="Explain agent node orchestration in two steps.",
                use_fake_cli=True,
            )
            self.assertIn("agent_results", result)
            self.assertEqual(result["agent_results"]["writer"]["status"], "completed")
            self.assertEqual(result["agent_results"]["reviewer"]["status"], "completed")
            self.assertIn("Explain agent node orchestration in two steps.", result["agent_results"]["reviewer"]["final_output"])
            self.assertTrue((Path(temp_dir) / ".workflow" / "agent" / "writer" / "config.json").exists())

    def test_real_demo_prepare_only_creates_claude_and_claude_sdk_folders(self) -> None:
        from workflow_agents.examples.real_agent_demo import ensure_demo_agent_directories

        with tempfile.TemporaryDirectory() as temp_dir:
            folders = ensure_demo_agent_directories(temp_dir)
            self.assertTrue(folders["claude"].joinpath("cli_args.json").exists())
            self.assertTrue(folders["claude_sdk"].joinpath("python_executable.txt").exists() is False)
            self.assertTrue(folders["claude_sdk"].joinpath("client_options.json").exists())
            self.assertTrue(folders["codex"].joinpath("cli_args.json").exists())

    def test_real_demo_builds_claude_sdk_writer_config_from_files(self) -> None:
        from workflow_agents.examples.real_agent_demo import _build_writer_config, ensure_demo_agent_directories

        with tempfile.TemporaryDirectory() as temp_dir:
            folders = ensure_demo_agent_directories(temp_dir)
            sdk_root = folders["claude_sdk"]
            sdk_root.joinpath("python_executable.txt").write_text(sys.executable + "\n", encoding="utf-8")
            sdk_root.joinpath("sdk_module.txt").write_text("claude_agent_sdk\n", encoding="utf-8")
            sdk_root.joinpath("cli_path.txt").write_text("C:/tools/claude.cmd\n", encoding="utf-8")
            sdk_root.joinpath("client_options.json").write_text(
                json.dumps({"permission_mode": "bypassPermissions"}, ensure_ascii=True),
                encoding="utf-8",
            )

            config = _build_writer_config(working_directory=temp_dir, claude_backend="claude_sdk")
            self.assertEqual(config.agent_type, "claude_sdk")
            self.assertEqual(config.executable_path, sys.executable)
            self.assertEqual(config.runtime_options["python_executable"], sys.executable)
            self.assertEqual(config.runtime_options["sdk_module"], "claude_agent_sdk")
            self.assertEqual(config.runtime_options["cli_path"], "C:/tools/claude.cmd")
            self.assertEqual(config.runtime_options["client_options"]["permission_mode"], "bypassPermissions")


if __name__ == "__main__":
    unittest.main()
