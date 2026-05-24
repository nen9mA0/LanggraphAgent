from __future__ import annotations

import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from workflow_agents import AgentNodeConfig, AgentRuntimeRegistry, materialize_reused_agent_config
    from workflow_agents.types import default_agent_config_directory
else:
    from .. import AgentNodeConfig, AgentRuntimeRegistry, materialize_reused_agent_config
    from ..types import default_agent_config_directory


def prepare_agent_directory(*, working_directory: str, home_directory: str | Path | None = None) -> Path:
    root = Path(working_directory).resolve()
    agent_root = default_agent_config_directory(working_directory=root, name="codex_demo", folder_name="codex_demo")
    materialize_reused_agent_config(
        agent_type="codex",
        source_working_directory=root,
        target_directory=agent_root,
        home_directory=home_directory,
        include_home_defaults=True,
        overwrite=True,
    )
    return agent_root


def build_config(*, working_directory: str, home_directory: str | Path | None = None) -> AgentNodeConfig:
    prepare_agent_directory(working_directory=working_directory, home_directory=home_directory)
    return AgentNodeConfig.from_provider_defaults(
        name="codex_demo",
        folder_name="codex_demo",
        agent_type="codex",
        working_directory=working_directory,
        home_directory=home_directory,
        system_prompt="You are a helpful coding assistant.",
        context_window_tokens=200_000,
        auto_start=False,
        startup_timeout_seconds=30.0,
        turn_timeout_seconds=300.0,
    )


def run_demo(*, working_directory: str) -> None:
    root = Path(working_directory).resolve()
    registry = AgentRuntimeRegistry(base_directory=root / ".workflow" / "agent")
    runtime = registry.get_or_create(build_config(working_directory=str(root), home_directory=Path.home()))
    try:
        runtime.start()
        print(f"runtime started, session_id={runtime.session_id!r}")
        print("input ':quit' to exit")

        while True:
            prompt = input("\n> ").strip()
            if not prompt:
                continue
            if prompt == ":quit":
                break

            turn_id = runtime.send_input(prompt)
            print(f"[turn_started] {turn_id}")
            print("[stream]")

            next_index = 0
            printed_text = False
            while not runtime.is_output_complete():
                for event in runtime.get_output_events(after_index=next_index):
                    next_index = event.index + 1
                    if event.event_type == "text" and event.content:
                        print(event.content, end="", flush=True)
                        printed_text = True
                time.sleep(0.2)

            for event in runtime.get_output_events(after_index=next_index):
                next_index = event.index + 1
                if event.event_type == "text" and event.content:
                    print(event.content, end="", flush=True)
                    printed_text = True

            if printed_text:
                print()

            result = runtime.wait_for_completion()
            print(f"\n[status] {result.status}")
            if result.session_id:
                print(f"[session_id] {result.session_id}")
            if result.error:
                print(f"[error] {result.error}")
            print("\n[usage]")
            print(result.usage.to_dict())
    finally:
        registry.shutdown_all()


if __name__ == "__main__":
    run_demo(working_directory=str(Path.cwd()))
