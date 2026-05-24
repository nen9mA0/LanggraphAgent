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
waiting_interrupt = False

def reply(message):
    print(json.dumps(message), flush=True)

# Fake Codex server used by runtime tests.
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
            "method": "turn/updated",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "running", "usage": {"input_tokens": 1, "output_tokens": 2}},
            },
        })
        reply({
            "jsonrpc": "2.0",
            "id": 9001,
            "method": "item/commandExecution/requestApproval",
            "params": {"command": "echo hidden", "reason": "test"},
        })
        reply({
            "jsonrpc": "2.0",
            "id": 9002,
            "method": "item/tool/requestUserInput",
            "params": {"itemId": "user-1", "threadId": thread_id, "turnId": turn_id, "questions": []},
        })
        reply({
            "jsonrpc": "2.0",
            "method": "item/reasoning/textDelta",
            "params": {"threadId": thread_id, "turnId": turn_id, "itemId": "reason-1", "delta": "thinking...", "contentIndex": 0},
        })
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
            "method": "item/commandExecution/outputDelta",
            "params": {"threadId": thread_id, "turnId": turn_id, "itemId": "cmd-1", "delta": "ok"},
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
            "method": "item/started",
            "params": {
                "threadId": thread_id,
                "item": {"id": "msg-1", "type": "agentMessage"},
            },
        })
        reply({
            "jsonrpc": "2.0",
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": "msg-1",
                "delta": f"stream:{prompt}",
            },
        })
        if "interrupt me" in prompt:
            waiting_interrupt = True
            continue
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
    elif "id" in payload and method == "turn/interrupt":
        reply({"jsonrpc": "2.0", "id": payload["id"], "result": {"status": "ok"}})
        if waiting_interrupt:
            waiting_interrupt = False
            reply({
                "jsonrpc": "2.0",
                "method": "turn/completed",
                "params": {
                    "threadId": thread_id,
                    "turn": {"id": payload["params"]["turnId"], "status": "interrupted", "usage": {"input_tokens": 4, "output_tokens": 4}},
                },
            })
    elif "id" in payload and payload["id"] in {9001, 9002}:
        continue
    elif "id" in payload:
        reply({"jsonrpc": "2.0", "id": payload["id"], "result": {}})
"""

FAKE_CODEX_SERVER_REQUESTS = """
import json
import sys

thread_id = "codex-thread-requests"
turn_id = "turn-1"

def reply(message):
    print(json.dumps(message), flush=True)

# Fake Codex server that exercises server-request handling.
for raw in sys.stdin:
    payload = json.loads(raw)
    method = payload.get("method")
    if "id" in payload and method == "initialize":
        reply({"jsonrpc": "2.0", "id": payload["id"], "result": {}})
    elif method == "initialized":
        continue
    elif "id" in payload and method in {"thread/start", "thread/resume"}:
        reply({"jsonrpc": "2.0", "id": payload["id"], "result": {"thread": {"id": thread_id}}})
    elif "id" in payload and method == "turn/start":
        reply({"jsonrpc": "2.0", "id": payload["id"], "result": {"turn": {"id": turn_id}}})
        reply({"jsonrpc": "2.0", "method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id}}})
        reply({"jsonrpc": "2.0", "id": 9010, "method": "item/tool/requestUserInput", "params": {"itemId": "user-1", "threadId": thread_id, "turnId": turn_id, "questions": []}})
        reply({
            "jsonrpc": "2.0",
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "item": {"id": "msg-1", "type": "agentMessage", "text": "final:request-path", "phase": "final_answer"},
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
    elif "id" in payload and payload["id"] == 9010:
        continue
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
            self.assertFalse(runtime.workspace.history_path.exists())
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
            try:
                first = runtime.run_turn("task one")
                self.assertEqual(first.status, "completed")
                self.assertEqual(first.final_output, "final:task one")
                self.assertEqual(first.session_id, "codex-thread-1")
                self.assertAlmostEqual(runtime.get_context_usage_ratio() or 0.0, 0.1)

                events = runtime.get_output_events()
                event_types = [event.event_type for event in events]
                self.assertIn("tool_use", event_types)
                self.assertIn("tool_result", event_types)
                self.assertIn("thinking", event_types)
                self.assertGreaterEqual(event_types.count("text"), 1)

                second = runtime.run_turn("task two")
                self.assertEqual(second.session_id, "codex-thread-1")
                self.assertEqual(second.final_output, "final:task two")
            finally:
                registry.shutdown_all()

    def test_codex_runtime_interrupts_active_turn_via_turn_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_codex = create_cmd_wrapper(Path(temp_dir), "fake_codex_interrupt", FAKE_CODEX)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            config = AgentNodeConfig(
                name="codex_interrupt_worker",
                agent_type="codex",
                executable_path=fake_codex,
                working_directory=temp_dir,
                context_window_tokens=100,
                turn_timeout_seconds=0.1,
            )

            runtime = registry.get_or_create(config)
            try:
                result = runtime.run_turn("interrupt me")
                self.assertEqual(result.status, "timeout")
                self.assertEqual(result.session_id, "codex-thread-1")
            finally:
                registry.shutdown_all()

    def test_codex_runtime_handles_server_request_user_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_codex = create_cmd_wrapper(Path(temp_dir), "fake_codex_requests", FAKE_CODEX_SERVER_REQUESTS)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            config = AgentNodeConfig(
                name="codex_request_worker",
                agent_type="codex",
                executable_path=fake_codex,
                working_directory=temp_dir,
                context_window_tokens=100,
            )

            runtime = registry.get_or_create(config)
            try:
                result = runtime.run_turn("request path")
                self.assertEqual(result.status, "completed")
                self.assertEqual(result.final_output, "final:request-path")
            finally:
                registry.shutdown_all()

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
                self.assertFalse(workspace.joinpath("history.jsonl").exists())
                inbox_lines = workspace.joinpath("inbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
                self.assertTrue(inbox_lines)
                self.assertNotIn("echo hidden", forwarded["content"])
            finally:
                registry.shutdown_all()

    def test_runtime_history_is_only_persisted_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_claude = create_cmd_wrapper(Path(temp_dir), "fake_claude_history", FAKE_CLAUDE)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            config = AgentNodeConfig(
                name="claude_history_writer",
                agent_type="claude",
                executable_path=fake_claude,
                working_directory=temp_dir,
                context_window_tokens=100,
                persist_runtime_history=True,
            )

            runtime = registry.get_or_create(config)
            try:
                result = runtime.run_turn("history please")
                self.assertEqual(result.status, "completed")
                self.assertTrue(runtime.workspace.history_path.exists())
                history_lines = runtime.workspace.history_path.read_text(encoding="utf-8").strip().splitlines()
                self.assertTrue(any('"kind": "turn_started"' in line for line in history_lines))
                self.assertTrue(any('"kind": "event"' in line for line in history_lines))
                self.assertTrue(any('"kind": "turn_completed"' in line for line in history_lines))
            finally:
                registry.shutdown_all()

    def test_node_mailbox_persistence_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_claude = create_cmd_wrapper(Path(temp_dir), "fake_claude_mailbox_off", FAKE_CLAUDE)
            registry = AgentRuntimeRegistry(base_directory=Path(temp_dir) / ".workflow" / "agent")
            try:
                node = AgentNode(
                    config=AgentNodeConfig(
                        name="writer",
                        agent_type="claude",
                        executable_path=fake_claude,
                        working_directory=temp_dir,
                        targets=("reviewer",),
                        persist_node_mailboxes=False,
                    ),
                    registry=registry,
                )

                state = {
                    "mailboxes": {
                        "writer": [
                            InterNodeMessage(sender="planner", recipient="writer", content="Draft section B").to_dict()
                        ]
                    }
                }
                result = node(state)
                workspace = Path(result["agent_results"]["writer"]["workspace"])
                self.assertFalse(workspace.joinpath("inbox.jsonl").exists())
                self.assertFalse(workspace.joinpath("outbox.jsonl").exists())
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

    def test_build_reused_agent_config_reads_minimal_claude_model(self) -> None:
        from workflow_agents.config_reuse import build_reused_agent_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".claude").mkdir(parents=True, exist_ok=True)
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-sonnet", "skills": ["skill-a"], "mcp": {"server": "x"}, "unused": {"x": 1}}, ensure_ascii=True),
                encoding="utf-8",
            )

            reused = build_reused_agent_config(agent_type="claude", working_directory=root, home_directory=root / "home")
            self.assertEqual(reused.model, "claude-sonnet")
            self.assertEqual(reused.runtime_options, {})
            self.assertEqual(reused.skills, [])
            self.assertEqual(reused.mcp, {})
            self.assertEqual(reused.metadata["source_kind"], "claude_settings")

    def test_build_reused_agent_config_reads_minimal_codex_model(self) -> None:
        from workflow_agents.config_reuse import build_reused_agent_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".codex").mkdir(parents=True, exist_ok=True)
            (root / ".codex" / "config.toml").write_text(
                'model = "gpt-5-codex"\nbase_url = "https://codex.example.test"\nmodel_provider = "openai"\nmodel_reasoning_effort = "high"\n',
                encoding="utf-8",
            )
            (root / ".codex" / "auth.json").write_text(
                json.dumps({"refresh_token": "secret-token"}, ensure_ascii=True),
                encoding="utf-8",
            )

            reused = build_reused_agent_config(agent_type="codex", working_directory=root, home_directory=root / "home")
            self.assertEqual(reused.model, "gpt-5-codex")
            self.assertEqual(reused.runtime_options["reused_base_url"], "https://codex.example.test")
            self.assertEqual(reused.runtime_options["reused_model_provider"], "openai")
            self.assertEqual(reused.runtime_options["reused_model_reasoning_effort"], "high")
            self.assertEqual(reused.auth, {"refresh_token": "secret-token"})
            self.assertEqual(reused.metadata["source_kind"], "codex_config_toml")

    def test_build_reused_agent_config_can_whitelist_skills_and_mcp(self) -> None:
        from workflow_agents.config_reuse import build_reused_agent_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".claude").mkdir(parents=True, exist_ok=True)
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-sonnet", "skills": ["skill-a", "skill-b"], "mcp": {"server": "x"}}, ensure_ascii=True),
                encoding="utf-8",
            )

            reused = build_reused_agent_config(
                agent_type="claude",
                working_directory=root,
                home_directory=root / "home",
                reuse_fields=("model", "skills", "mcp"),
            )
            self.assertEqual(reused.model, "claude-sonnet")
            self.assertEqual(reused.skills, ["skill-a", "skill-b"])
            self.assertEqual(reused.mcp, {"server": "x"})

    def test_agent_node_config_from_provider_defaults_reuses_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agent_root = root / ".workflow" / "agent" / "writer"
            (agent_root / ".claude").mkdir(parents=True, exist_ok=True)
            (agent_root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-default"}, ensure_ascii=True),
                encoding="utf-8",
            )

            config = AgentNodeConfig.from_provider_defaults(
                name="writer",
                agent_type="claude",
                working_directory=root,
                executable_path="claude",
                home_directory=root / "home",
            )
            self.assertEqual(config.model, "claude-default")
            self.assertNotIn("reused_skills", config.runtime_options)
            self.assertNotIn("reused_mcp", config.runtime_options)

    def test_agent_node_config_from_provider_defaults_can_enable_skills_and_mcp_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agent_root = root / ".workflow" / "agent" / "writer"
            (agent_root / ".claude").mkdir(parents=True, exist_ok=True)
            (agent_root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-default", "skills": ["skill-a"], "mcp": {"server": "x"}}, ensure_ascii=True),
                encoding="utf-8",
            )

            config = AgentNodeConfig.from_provider_defaults(
                name="writer",
                agent_type="claude",
                working_directory=root,
                executable_path="claude",
                home_directory=root / "home",
                reuse_fields=("model", "skills", "mcp"),
            )
            self.assertEqual(config.model, "claude-default")
            self.assertEqual(config.runtime_options["reused_skills"], ["skill-a"])
            self.assertEqual(config.runtime_options["reused_mcp"], {"server": "x"})

    def test_agent_node_config_from_provider_defaults_allows_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            agent_root = root / ".workflow" / "agent" / "reviewer"
            (agent_root / ".codex").mkdir(parents=True, exist_ok=True)
            (agent_root / ".codex" / "config.toml").write_text(
                'model = "gpt-5-codex"\nmodel_provider = "openai"\n',
                encoding="utf-8",
            )

            config = AgentNodeConfig.from_provider_defaults(
                name="reviewer",
                agent_type="codex",
                working_directory=root,
                executable_path="codex",
                model="custom-model",
                runtime_options={"reused_model_provider": "custom-provider", "x": 1},
                home_directory=root / "home",
            )
            self.assertEqual(config.model, "custom-model")
            self.assertEqual(config.runtime_options["reused_model_provider"], "custom-provider")
            self.assertEqual(config.runtime_options["x"], 1)

    def test_materialize_reused_agent_config_writes_minimal_claude_snapshot(self) -> None:
        from workflow_agents.config_reuse import materialize_reused_agent_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "project"
            target_root = root / "agent" / "claude_writer"
            (source_root / ".claude").mkdir(parents=True, exist_ok=True)
            (source_root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-opus", "unused": {"x": 1}}, ensure_ascii=True),
                encoding="utf-8",
            )

            snapshot = materialize_reused_agent_config(
                agent_type="claude",
                source_working_directory=source_root,
                target_directory=target_root,
            )
            config_path = target_root / ".claude" / "settings.json"
            self.assertEqual(snapshot.agent_type, "claude")
            self.assertEqual(snapshot.written_files, [config_path.resolve()])
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8")), {"model": "claude-opus"})

    def test_materialize_reused_agent_config_writes_minimal_codex_snapshot(self) -> None:
        from workflow_agents.config_reuse import materialize_reused_agent_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "project"
            target_root = root / "agent" / "codex_reviewer"
            (source_root / ".codex").mkdir(parents=True, exist_ok=True)
            (source_root / ".codex" / "config.toml").write_text(
                'model = "gpt-5-codex"\nbase_url = "https://codex.example.test"\nmodel_provider = "openai"\nmodel_reasoning_effort = "high"\n',
                encoding="utf-8",
            )
            (source_root / ".codex" / "auth.json").write_text(
                json.dumps({"refresh_token": "secret-token"}, ensure_ascii=True),
                encoding="utf-8",
            )

            snapshot = materialize_reused_agent_config(
                agent_type="codex",
                source_working_directory=source_root,
                target_directory=target_root,
                home_directory=root / "home",
            )
            config_path = target_root / ".codex" / "config.toml"
            auth_path = target_root / ".codex" / "auth.json"
            self.assertEqual(snapshot.agent_type, "codex")
            self.assertEqual(snapshot.written_files, [config_path.resolve(), auth_path.resolve()])
            content = config_path.read_text(encoding="utf-8")
            self.assertIn('model = "gpt-5-codex"', content)
            self.assertIn('base_url = "https://codex.example.test"', content)
            self.assertIn('model_provider = "openai"', content)
            self.assertIn('model_reasoning_effort = "high"', content)
            self.assertEqual(json.loads(auth_path.read_text(encoding="utf-8")), {"refresh_token": "secret-token"})

    def test_materialize_reused_agent_config_can_ignore_home_defaults(self) -> None:
        from workflow_agents.config_reuse import materialize_reused_agent_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "project"
            target_root = root / "agent" / "codex_reviewer"
            home_root = root / "home"
            (home_root / ".codex").mkdir(parents=True, exist_ok=True)
            (home_root / ".codex" / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")
            (source_root / ".codex").mkdir(parents=True, exist_ok=True)
            (source_root / ".codex" / "config.toml").write_text('model = "gpt-5-codex"\n', encoding="utf-8")

            snapshot = materialize_reused_agent_config(
                agent_type="codex",
                source_working_directory=source_root,
                target_directory=target_root,
                home_directory=home_root,
                include_home_defaults=False,
            )
            content = target_root.joinpath(".codex", "config.toml").read_text(encoding="utf-8")
            self.assertEqual(snapshot.agent_type, "codex")
            self.assertIn('model = "gpt-5-codex"', content)
            self.assertNotIn('model = "gpt-5.4"', content)

    def test_claude_runtime_prepares_reused_skills_and_mcp_artifacts(self) -> None:
        from workflow_agents.runtime.claude import ClaudeCodeRuntime
        from workflow_agents.storage import AgentWorkspace

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "skills" / "writer_skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_dir.joinpath("SKILL.md").write_text("# writer skill\n", encoding="utf-8")
            workspace = AgentWorkspace(node_name="writer", folder_name="writer", root=root / ".workflow" / "agent" / "writer")
            workspace.ensure()
            config = AgentNodeConfig(
                name="writer",
                folder_name="writer",
                agent_type="claude",
                executable_path="claude",
                working_directory=temp_dir,
                auto_start=False,
                runtime_options={
                    "reused_skills": [str(skill_dir)],
                    "reused_mcp": {"demo": {"command": "demo-mcp", "args": ["--stdio"]}},
                },
            )

            runtime = ClaudeCodeRuntime(config, workspace)
            config_dir = runtime._prepare_reused_config_dir()
            mcp_path = runtime._prepare_reused_mcp_config()

            self.assertIsNotNone(config_dir)
            self.assertTrue(config_dir.joinpath("skills", "writer_skill", "SKILL.md").exists())
            self.assertIsNotNone(mcp_path)
            self.assertEqual(
                json.loads(mcp_path.read_text(encoding="utf-8")),
                {"mcpServers": {"demo": {"command": "demo-mcp", "args": ["--stdio"]}}},
            )
            args = runtime._build_args()
            self.assertIn("--mcp-config", args)
            self.assertIn(str(mcp_path), args)

    def test_codex_runtime_builds_config_override_args_for_reused_skills_and_mcp(self) -> None:
        from workflow_agents.runtime.codex import CodexRuntime
        from workflow_agents.storage import AgentWorkspace

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = AgentWorkspace(node_name="reviewer", folder_name="reviewer", root=root / ".workflow" / "agent" / "reviewer")
            workspace.ensure()
            config = AgentNodeConfig(
                name="reviewer",
                folder_name="reviewer",
                agent_type="codex",
                executable_path="codex",
                working_directory=temp_dir,
                auto_start=False,
                runtime_options={
                    "reused_skills": ["skill-a", "skill-b"],
                    "reused_mcp": {"demo": {"command": "demo-mcp", "args": ["--stdio"]}},
                    "reused_model_provider": "openai",
                    "reused_model_reasoning_effort": "high",
                },
            )

            runtime = CodexRuntime(config, workspace)
            args = runtime._config_override_args()
            joined = " ".join(args)
            self.assertIn("skills.config=", joined)
            self.assertIn("mcp_servers=", joined)
            self.assertIn("model_provider=", joined)
            self.assertIn("model_reasoning_effort=", joined)
            self.assertIn('"skill-a"', joined)
            self.assertIn('"demo"', joined)

    def test_codex_runtime_prepares_local_codex_home_with_reused_auth_and_base_url(self) -> None:
        from workflow_agents.runtime.codex import CodexRuntime
        from workflow_agents.storage import AgentWorkspace

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = AgentWorkspace(node_name="reviewer", folder_name="reviewer", root=root / ".workflow" / "agent" / "reviewer")
            workspace.ensure()
            config = AgentNodeConfig(
                name="reviewer",
                folder_name="reviewer",
                agent_type="codex",
                executable_path="codex",
                working_directory=temp_dir,
                auto_start=False,
                model="gpt-5-codex",
                runtime_options={
                    "reused_base_url": "https://codex.example.test",
                    "reused_model_provider": "openai",
                    "reused_model_reasoning_effort": "high",
                    "reused_auth": {"refresh_token": "secret-token"},
                },
            )

            runtime = CodexRuntime(config, workspace)
            codex_home = runtime._prepare_codex_home()

            self.assertEqual(codex_home, workspace.root / ".codex")
            self.assertIn('base_url = "https://codex.example.test"', codex_home.joinpath("config.toml").read_text(encoding="utf-8"))
            self.assertIn('model = "gpt-5-codex"', codex_home.joinpath("config.toml").read_text(encoding="utf-8"))
            self.assertEqual(
                json.loads(codex_home.joinpath("auth.json").read_text(encoding="utf-8")),
                {"refresh_token": "secret-token"},
            )

    def test_claude_sdk_worker_config_includes_mcp_and_env(self) -> None:
        from workflow_agents.runtime.claude_sdk import ClaudeSDKRuntime
        from workflow_agents.storage import AgentWorkspace

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill_dir = root / "skills" / "writer_skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_dir.joinpath("SKILL.md").write_text("# writer skill\n", encoding="utf-8")
            workspace = AgentWorkspace(
                node_name="writer_sdk",
                folder_name="writer_sdk",
                root=root / ".workflow" / "agent" / "writer_sdk",
            )
            workspace.ensure()
            config = AgentNodeConfig(
                name="writer_sdk",
                folder_name="writer_sdk",
                agent_type="claude_sdk",
                executable_path=sys.executable,
                working_directory=temp_dir,
                auto_start=False,
                env={"EXTRA_ENV": "1"},
                runtime_options={
                    "python_executable": sys.executable,
                    "reused_skills": [str(skill_dir)],
                    "reused_mcp": {"demo": {"command": "demo-mcp"}},
                },
            )

            runtime = ClaudeSDKRuntime(config, workspace)
            payload = json.loads(runtime._worker_config_payload())
            self.assertEqual(payload["env"]["EXTRA_ENV"], "1")
            self.assertTrue(payload["env"]["CLAUDE_CONFIG_DIR"])
            self.assertTrue(payload["mcp_config_path"])
            self.assertTrue(Path(payload["mcp_config_path"]).exists())
            self.assertTrue(Path(payload["env"]["CLAUDE_CONFIG_DIR"]).joinpath("skills", "writer_skill", "SKILL.md").exists())

    def test_agent_node_config_from_provider_defaults_prefers_local_snapshot_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_root = root / "project"
            agent_root = project_root / ".workflow" / "agent" / "writer"
            (agent_root / ".claude").mkdir(parents=True, exist_ok=True)
            (agent_root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-local-snapshot"}, ensure_ascii=True),
                encoding="utf-8",
            )

            config = AgentNodeConfig.from_provider_defaults(
                name="writer",
                agent_type="claude",
                working_directory=project_root,
                executable_path="claude",
            )
            self.assertEqual(config.model, "claude-local-snapshot")

    def test_real_demo_config_reuses_provider_model_settings(self) -> None:
        from workflow_agents.examples.real_agent_demo import (
            _build_reviewer_config,
            _build_writer_config,
            ensure_demo_agent_directories,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ensure_demo_agent_directories(temp_dir)
            (root / ".claude").mkdir(parents=True, exist_ok=True)
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-opus"}, ensure_ascii=True),
                encoding="utf-8",
            )
            (root / ".codex").mkdir(parents=True, exist_ok=True)
            (root / ".codex" / "config.toml").write_text('model = "gpt-5-codex"\n', encoding="utf-8")
            sdk_root = root / ".workflow" / "agent" / "claude_sdk_writer"
            sdk_root.joinpath("python_executable.txt").write_text(sys.executable + "\n", encoding="utf-8")

            writer_config = _build_writer_config(working_directory=temp_dir, claude_backend="claude")
            reviewer_config = _build_reviewer_config(working_directory=temp_dir)
            sdk_writer_config = _build_writer_config(working_directory=temp_dir, claude_backend="claude_sdk")

            self.assertEqual(writer_config.model, "claude-opus")
            self.assertEqual(sdk_writer_config.model, "claude-opus")
            self.assertEqual(reviewer_config.model, "gpt-5-codex")

    def test_real_demo_prepare_materializes_local_provider_snapshots(self) -> None:
        from workflow_agents.examples.real_agent_demo import ensure_demo_agent_directories

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".claude").mkdir(parents=True, exist_ok=True)
            (root / ".claude" / "settings.json").write_text(
                json.dumps({"model": "claude-opus"}, ensure_ascii=True),
                encoding="utf-8",
            )
            (root / ".codex").mkdir(parents=True, exist_ok=True)
            (root / ".codex" / "config.toml").write_text('model = "gpt-5-codex"\n', encoding="utf-8")

            folders = ensure_demo_agent_directories(temp_dir)
            self.assertEqual(
                json.loads(folders["claude"].joinpath(".claude", "settings.json").read_text(encoding="utf-8")),
                {"model": "claude-opus"},
            )
            self.assertEqual(
                json.loads(folders["claude_sdk"].joinpath(".claude", "settings.json").read_text(encoding="utf-8")),
                {"model": "claude-opus"},
            )
            self.assertIn('model = "gpt-5-codex"', folders["codex"].joinpath(".codex", "config.toml").read_text(encoding="utf-8"))

    def test_agent_example_reuses_provider_model_settings(self) -> None:
        from workflow_agents.examples.agent_example import build_config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".codex").mkdir(parents=True, exist_ok=True)
            (root / ".codex" / "config.toml").write_text(
                'model = "gpt-5-codex"\nbase_url = "https://codex.example.test"\nmodel_provider = "openai"\nmodel_reasoning_effort = "high"\n',
                encoding="utf-8",
            )
            (root / ".codex" / "auth.json").write_text(
                json.dumps({"refresh_token": "secret-token"}, ensure_ascii=True),
                encoding="utf-8",
            )

            config = build_config(working_directory=temp_dir, home_directory=root / "home")

            self.assertEqual(config.folder_name, "codex_demo")
            self.assertEqual(config.model, "gpt-5-codex")
            self.assertEqual(config.runtime_options["reused_base_url"], "https://codex.example.test")
            self.assertEqual(config.runtime_options["reused_model_provider"], "openai")
            self.assertEqual(config.runtime_options["reused_model_reasoning_effort"], "high")
            self.assertEqual(config.runtime_options["reused_auth"], {"refresh_token": "secret-token"})


if __name__ == "__main__":
    unittest.main()
