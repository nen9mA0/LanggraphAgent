from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..node import AgentNode
from ..registry import AgentRuntimeRegistry
from ..state import AgentGraphState
from ..types import AgentNodeConfig, InterNodeMessage

CLAUDE_FOLDER = "claude_writer"
CODEX_FOLDER = "codex_reviewer"


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_demo_agent_directories(working_directory: str) -> dict[str, Path]:
    root = Path(working_directory).resolve()
    agent_root = root / ".workflow" / "agent"
    claude_root = agent_root / CLAUDE_FOLDER
    codex_root = agent_root / CODEX_FOLDER
    for folder in (claude_root, codex_root):
        folder.mkdir(parents=True, exist_ok=True)

    _ensure_template_files(
        claude_root,
        agent_type="claude",
        default_system_prompt="You are the writer node. Produce a concise draft for the reviewer node.",
    )
    _ensure_template_files(
        codex_root,
        agent_type="codex",
        default_system_prompt="You are the reviewer node. Review the writer output and return the final answer.",
    )
    return {"claude": claude_root, "codex": codex_root}


def _ensure_template_files(root: Path, *, agent_type: str, default_system_prompt: str) -> None:
    files: dict[str, str] = {
        "system_prompt.txt": default_system_prompt + "\n",
        "cli_args.json": "[]\n",
        "env.json": "{}\n",
        "README.txt": (
            f"Folder: {root.name}\n"
            f"Agent type: {agent_type}\n\n"
            "Fill these files before running the real demo if needed:\n"
            "- system_prompt.txt: system prompt appended to the agent\n"
            "- cli_args.json: JSON array of extra CLI arguments\n"
            "- env.json: JSON object of environment variables\n\n"
            "Optional:\n"
            "- runtime.json will be written automatically after first run\n"
            "- history.jsonl / inbox.jsonl / outbox.jsonl will be written automatically during runs\n"
        ),
    }
    for filename, content in files.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def planner_node(state: AgentGraphState) -> AgentGraphState:
    topic = (state.get("shared") or {}).get("topic", "Please produce a short draft.")
    message = InterNodeMessage(
        sender="planner",
        recipient="writer",
        content=(
            "Write a draft that will be reviewed by another agent.\n"
            "Keep the content concrete and complete.\n\n"
            f"Topic:\n{topic}"
        ),
    )
    return {"mailboxes": {"writer": [message.to_dict()]}}


def build_real_demo_graph(registry: AgentRuntimeRegistry, working_directory: str) -> Any:
    from langgraph.graph import END, START, StateGraph

    root = Path(working_directory).resolve()
    claude_root = root / ".workflow" / "agent" / CLAUDE_FOLDER
    codex_root = root / ".workflow" / "agent" / CODEX_FOLDER

    writer = AgentNode(
        config=AgentNodeConfig(
            name="writer",
            folder_name=CLAUDE_FOLDER,
            agent_type="claude",
            executable_path="claude",
            working_directory=working_directory,
            system_prompt=_load_text(claude_root / "system_prompt.txt"),
            cli_args=tuple(_load_optional_json(claude_root / "cli_args.json")),
            env={str(k): str(v) for k, v in _load_optional_json(claude_root / "env.json").items()},
            targets=("reviewer",),
            context_window_tokens=200_000,
            prompt_prefix=(
                "Produce the writer result only. Do not mention internal tool traces. "
                "Your output will be forwarded to a reviewer node."
            ),
        ),
        registry=registry,
    )
    reviewer = AgentNode(
        config=AgentNodeConfig(
            name="reviewer",
            folder_name=CODEX_FOLDER,
            agent_type="codex",
            executable_path="codex",
            working_directory=working_directory,
            system_prompt=_load_text(codex_root / "system_prompt.txt"),
            cli_args=tuple(_load_optional_json(codex_root / "cli_args.json")),
            env={str(k): str(v) for k, v in _load_optional_json(codex_root / "env.json").items()},
            context_window_tokens=200_000,
            prompt_prefix=(
                "Review the writer output and return the final answer only. "
                "Do not include internal execution details."
            ),
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


def run_real_demo(*, working_directory: str, topic: str) -> dict[str, Any]:
    root = Path(working_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ensure_demo_agent_directories(str(root))
    registry = AgentRuntimeRegistry(base_directory=root / ".workflow" / "agent")
    try:
        app = build_real_demo_graph(registry, str(root))
        result = app.invoke({"shared": {"topic": topic}})
        return dict(result)
    finally:
        registry.shutdown_all()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a real Claude + Codex workflow_agents LangGraph demo.")
    parser.add_argument(
        "--working-directory",
        default=str(Path.cwd()),
        help="Workspace used by both agents. Default: current directory.",
    )
    parser.add_argument(
        "--topic",
        default="Write and review a short explanation of why agent nodes should be long-lived.",
        help="Initial topic sent by the planner node.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only create the .workflow/agent folders and template config files, then exit.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    folders = ensure_demo_agent_directories(args.working_directory)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "prepared": True,
                    "claude_folder": str(folders["claude"]),
                    "codex_folder": str(folders["codex"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    result = run_real_demo(working_directory=args.working_directory, topic=args.topic)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
