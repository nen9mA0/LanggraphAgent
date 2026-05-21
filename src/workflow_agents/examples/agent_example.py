import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workflow_agents import AgentNodeConfig, AgentRuntimeRegistry

script_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = Path(script_dir) / ".workflow" / "agent"

def build_runtime():
    registry = AgentRuntimeRegistry(base_directory=workspace_root)
    config = AgentNodeConfig(
        name="codex_node",
        folder_name="codex_node",
        agent_type="codex",
        working_directory=str(workspace_root),
        auto_start=False,
        startup_timeout_seconds=30.0,
        turn_timeout_seconds=300.0,
        context_window_tokens=200_000,
        system_prompt="You are a helpful coding assistant.",
    )
    runtime = registry.get_or_create(config)
    return registry, runtime

def run_streaming_demo() -> None:
    registry, runtime = build_runtime()
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
                events = runtime.get_output_events(after_index=next_index)
                for event in events:
                    next_index = event.index + 1
                    if event.event_type == "text" and event.content:
                        print(event.content, end="", flush=True)
                        printed_text = True
                time.sleep(0.2)

            events = runtime.get_output_events(after_index=next_index)
            for event in events:
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
    run_streaming_demo()