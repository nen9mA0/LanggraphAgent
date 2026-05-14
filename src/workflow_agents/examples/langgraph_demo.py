from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from ..node import AgentNode
from ..registry import AgentRuntimeRegistry
from ..state import AgentGraphState
from ..types import AgentNodeConfig, InterNodeMessage
from .demo_support import (
    FAKE_CLAUDE_SCRIPT,
    FAKE_CODEX_SCRIPT,
    create_windows_cmd_wrapper,
)


def planner_node(state: AgentGraphState) -> AgentGraphState:
    topic = (state.get("shared") or {}).get("topic", "Write a short workflow summary.")
    message = InterNodeMessage(
        sender="planner",
        recipient="writer",
        content=f"Please draft a response for this topic:\n{topic}",
    )
    return {"mailboxes": {"writer": [message.to_dict()]}}


def build_demo_graph(
    registry: AgentRuntimeRegistry,
    working_directory: str,
    *,
    claude_executable: str,
    codex_executable: str,
) -> Any:
    from langgraph.graph import END, START, StateGraph

    writer = AgentNode(
        config=AgentNodeConfig(
            name="writer",
            agent_type="claude",
            executable_path=claude_executable,
            working_directory=working_directory,
            targets=("reviewer",),
            context_window_tokens=200_000,
            prompt_prefix="Return a clean draft for the downstream reviewer.",
        ),
        registry=registry,
    )
    reviewer = AgentNode(
        config=AgentNodeConfig(
            name="reviewer",
            agent_type="codex",
            executable_path=codex_executable,
            working_directory=working_directory,
            context_window_tokens=200_000,
            prompt_prefix="Review the writer output and return the final answer.",
        ),
        registry=registry,
    )

    graph = StateGraph(AgentGraphState)
    graph.add_node("planner", planner_node)
    graph.add_node("writer", writer)
    graph.add_node("reviewer", reviewer)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "writer")
    graph.add_edge("writer", "reviewer")
    graph.add_edge("reviewer", END)
    return graph.compile()


def run_demo(
    *,
    working_directory: str,
    topic: str,
    use_fake_cli: bool = False,
    claude_executable: str | None = None,
    codex_executable: str | None = None,
) -> dict[str, Any]:
    runtime_root = Path(working_directory).resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    registry = AgentRuntimeRegistry(base_directory=runtime_root / ".workflow" / "agent")

    fake_cli_temp: tempfile.TemporaryDirectory[str] | None = None
    try:
        if use_fake_cli:
            fake_cli_temp = tempfile.TemporaryDirectory()
            fake_root = Path(fake_cli_temp.name)
            claude_executable = create_windows_cmd_wrapper(fake_root, "fake_claude_demo", FAKE_CLAUDE_SCRIPT)
            codex_executable = create_windows_cmd_wrapper(fake_root, "fake_codex_demo", FAKE_CODEX_SCRIPT)
        if not claude_executable or not codex_executable:
            raise ValueError("claude_executable and codex_executable are required when use_fake_cli is false")

        app = build_demo_graph(
            registry,
            str(runtime_root),
            claude_executable=claude_executable,
            codex_executable=codex_executable,
        )
        result = app.invoke({"shared": {"topic": topic}})
        return dict(result)
    finally:
        registry.shutdown_all()
        if fake_cli_temp is not None:
            fake_cli_temp.cleanup()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the workflow_agents LangGraph demo.")
    parser.add_argument(
        "--working-directory",
        default=str(Path.cwd() / ".demo_workdir"),
        help="Directory used by the agent runtimes. Default: ./.demo_workdir",
    )
    parser.add_argument(
        "--topic",
        default="Summarize why long-lived CLI agents are useful as LangGraph nodes.",
        help="Initial topic sent from planner to writer.",
    )
    parser.add_argument(
        "--use-fake-cli",
        action="store_true",
        help="Generate local fake Claude/Codex wrappers so the demo can run without real agent CLIs.",
    )
    parser.add_argument("--claude-exec", default=None, help="Path to the real claude executable.")
    parser.add_argument("--codex-exec", default=None, help="Path to the real codex executable.")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result = run_demo(
        working_directory=args.working_directory,
        topic=args.topic,
        use_fake_cli=args.use_fake_cli,
        claude_executable=args.claude_exec,
        codex_executable=args.codex_exec,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
