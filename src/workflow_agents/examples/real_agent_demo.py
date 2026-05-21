from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..config_reuse import materialize_reused_agent_config
from ..node import AgentNode
from ..registry import AgentRuntimeRegistry
from ..state import AgentGraphState
from ..types import AgentNodeConfig, InterNodeMessage

CLAUDE_FOLDER = "claude_writer"
CLAUDE_SDK_FOLDER = "claude_sdk_writer"
CODEX_FOLDER = "codex_reviewer"


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected JSON array in {path}")
    return list(payload)


def ensure_demo_agent_directories(working_directory: str) -> dict[str, Path]:
    root = Path(working_directory).resolve()
    agent_root = root / ".workflow" / "agent"
    claude_root = agent_root / CLAUDE_FOLDER
    claude_sdk_root = agent_root / CLAUDE_SDK_FOLDER
    codex_root = agent_root / CODEX_FOLDER
    for folder in (claude_root, claude_sdk_root, codex_root):
        folder.mkdir(parents=True, exist_ok=True)

    _ensure_template_files(
        claude_root,
        agent_type="claude",
        default_system_prompt="You are the writer node. Produce a concise draft for the reviewer node.",
    )
    materialize_reused_agent_config(
        agent_type="claude",
        source_working_directory=root,
        target_directory=claude_root,
        reuse_fields=("model",),
        include_home_defaults=False,
    )
    _ensure_claude_sdk_template_files(
        claude_sdk_root,
        default_system_prompt="You are the writer node. Produce a concise draft for the reviewer node.",
    )
    materialize_reused_agent_config(
        agent_type="claude_sdk",
        source_working_directory=root,
        target_directory=claude_sdk_root,
        reuse_fields=("model",),
        include_home_defaults=False,
    )
    _ensure_template_files(
        codex_root,
        agent_type="codex",
        default_system_prompt="You are the reviewer node. Review the writer output and return the final answer.",
    )
    materialize_reused_agent_config(
        agent_type="codex",
        source_working_directory=root,
        target_directory=codex_root,
        reuse_fields=("model",),
        include_home_defaults=False,
    )
    return {"claude": claude_root, "claude_sdk": claude_sdk_root, "codex": codex_root}


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
            "Provider config reuse:\n"
            "- .claude/settings.json or .codex/config.toml may be generated automatically\n"
            "- only the minimal reusable subset is copied, currently focused on model settings\n"
            "- edit these local files if you want this node to diverge from the project-level defaults\n\n"
            "Optional:\n"
            "- runtime.json will be written automatically after first run\n"
            "- inbox.jsonl / outbox.jsonl will be written automatically during runs\n"
            "- history.jsonl is only written when runtime history persistence is explicitly enabled\n"
        ),
    }
    for filename, content in files.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _ensure_claude_sdk_template_files(root: Path, *, default_system_prompt: str) -> None:
    files: dict[str, str] = {
        "system_prompt.txt": default_system_prompt + "\n",
        "env.json": "{}\n",
        "client_options.json": "{}\n",
        "README.txt": (
            f"Folder: {root.name}\n"
            "Agent type: claude_sdk\n\n"
            "Required before running:\n"
            "- python_executable.txt: absolute path to the Python interpreter that can import claude_agent_sdk\n\n"
            "Optional:\n"
            "- sdk_module.txt: SDK import name, default is claude_agent_sdk\n"
            "- cli_path.txt: path to the claude CLI used by the SDK\n"
            "- system_prompt.txt: system prompt for the writer node\n"
            "- env.json: JSON object of environment variables for the worker process\n"
            "- client_options.json: JSON object forwarded into ClaudeAgentOptions(...)\n\n"
            "Provider config reuse:\n"
            "- .claude/settings.json may be generated automatically as a minimal local snapshot\n"
            "- by default only model-related settings are copied\n"
            "- extend this local snapshot later if you want to reuse more provider-native fields\n\n"
            "Generated during runs:\n"
            "- config.json\n"
            "- runtime.json\n"
            "- inbox.jsonl / outbox.jsonl\n"
            "- history.jsonl only when runtime history persistence is explicitly enabled\n"
        ),
    }
    for filename, content in files.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _select_writer_folder(claude_backend: str) -> str:
    if claude_backend == "claude":
        return CLAUDE_FOLDER
    if claude_backend == "claude_sdk":
        return CLAUDE_SDK_FOLDER
    raise ValueError(f"unsupported claude backend: {claude_backend}")


def _build_writer_config(*, working_directory: str, claude_backend: str) -> AgentNodeConfig:
    root = Path(working_directory).resolve()
    folder_name = _select_writer_folder(claude_backend)
    writer_root = root / ".workflow" / "agent" / folder_name
    common_kwargs = {
        "name": "writer",
        "folder_name": folder_name,
        "working_directory": working_directory,
        "system_prompt": _load_text(writer_root / "system_prompt.txt"),
        "env": {str(k): str(v) for k, v in _load_optional_json(writer_root / "env.json").items()},
        "targets": ("reviewer",),
        "context_window_tokens": 200_000,
        "persist_runtime_history": False,
        "persist_node_mailboxes": True,
        "prompt_prefix": (
            "Produce the writer result only. Do not mention internal tool traces. "
            "Your output will be forwarded to a reviewer node."
        ),
    }
    if claude_backend == "claude":
        return AgentNodeConfig.from_provider_defaults(
            agent_type="claude",
            executable_path="claude",
            provider_config_directory=writer_root,
            cli_args=tuple(str(item) for item in _load_optional_json_list(writer_root / "cli_args.json")),
            **common_kwargs,
        )

    python_executable = _load_text(writer_root / "python_executable.txt")
    if not python_executable:
        raise ValueError(
            f"missing python_executable.txt in {writer_root}; it must point to a Python interpreter that can import claude_agent_sdk"
        )
    sdk_module = _load_text(writer_root / "sdk_module.txt") or "claude_agent_sdk"
    cli_path = _load_text(writer_root / "cli_path.txt")
    return AgentNodeConfig.from_provider_defaults(
        agent_type="claude_sdk",
        executable_path=python_executable,
        provider_config_directory=writer_root,
        runtime_options={
            "python_executable": python_executable,
            "sdk_module": sdk_module,
            "cli_path": cli_path or None,
            "client_options": _load_optional_json(writer_root / "client_options.json"),
        },
        **common_kwargs,
    )


def _build_reviewer_config(*, working_directory: str) -> AgentNodeConfig:
    root = Path(working_directory).resolve()
    codex_root = root / ".workflow" / "agent" / CODEX_FOLDER
    return AgentNodeConfig.from_provider_defaults(
        name="reviewer",
        folder_name=CODEX_FOLDER,
        agent_type="codex",
        executable_path="codex",
        provider_config_directory=codex_root,
        working_directory=working_directory,
        system_prompt=_load_text(codex_root / "system_prompt.txt"),
        cli_args=tuple(str(item) for item in _load_optional_json_list(codex_root / "cli_args.json")),
        env={str(k): str(v) for k, v in _load_optional_json(codex_root / "env.json").items()},
        context_window_tokens=200_000,
        persist_runtime_history=False,
        persist_node_mailboxes=True,
        prompt_prefix=(
            "Review the writer output and return the final answer only. "
            "Do not include internal execution details."
        ),
    )


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


def build_real_demo_graph(registry: AgentRuntimeRegistry, working_directory: str, *, claude_backend: str = "claude") -> Any:
    from langgraph.graph import END, START, StateGraph

    writer = AgentNode(
        config=_build_writer_config(working_directory=working_directory, claude_backend=claude_backend),
        registry=registry,
    )
    reviewer = AgentNode(
        config=_build_reviewer_config(working_directory=working_directory),
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


def run_real_demo(*, working_directory: str, topic: str, claude_backend: str = "claude") -> dict[str, Any]:
    root = Path(working_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ensure_demo_agent_directories(str(root))
    registry = AgentRuntimeRegistry(base_directory=root / ".workflow" / "agent")
    try:
        app = build_real_demo_graph(registry, str(root), claude_backend=claude_backend)
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
        "--claude-backend",
        choices=("claude", "claude_sdk"),
        default="claude",
        help="Choose whether the writer node uses the Claude CLI runtime or the Claude Python SDK runtime.",
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
                    "claude_sdk_folder": str(folders["claude_sdk"]),
                    "codex_folder": str(folders["codex"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    result = run_real_demo(
        working_directory=args.working_directory,
        topic=args.topic,
        claude_backend=args.claude_backend,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
