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


if __name__ == "__main__":
    unittest.main()
