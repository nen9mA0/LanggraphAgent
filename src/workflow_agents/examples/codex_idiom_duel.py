from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from workflow_agents import AgentNode, AgentNodeConfig, AgentRuntimeRegistry, InterNodeMessage, apply_reused_agent_config, build_reused_agent_config, write_reused_agent_config
    from workflow_agents.state import AgentGraphState
    from workflow_agents.types import default_agent_config_directory
else:
    from .. import AgentNode, AgentNodeConfig, AgentRuntimeRegistry, InterNodeMessage, apply_reused_agent_config, build_reused_agent_config, write_reused_agent_config
    from ..state import AgentGraphState
    from ..types import default_agent_config_directory


PLAYER_A_FOLDER = "codex_idiom_player_a"
PLAYER_B_FOLDER = "codex_idiom_player_b"
DEFAULT_SEED_IDIOM = "胸有成竹"
DEFAULT_MAX_ROUNDS = 8

CONTINUE_RE = re.compile(r"^\s*继续[:：]\s*([\u4e00-\u9fff]{4,8})\s*$")
STOP_RE = re.compile(r"^\s*停止[:：]?\s*(.*)$")
IDIOM_RE = re.compile(r"[\u4e00-\u9fff]{4,8}")


@dataclass(slots=True)
class ParsedIdiomReply:
    action: str
    idiom: str = ""
    reason: str = ""


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


def _ensure_template_files(root: Path, *, player_label: str) -> None:
    files: dict[str, str] = {
        "system_prompt.txt": (
            f"你是成语接龙选手{player_label}。\n"
            "你正在和另一个 Codex agent 玩成语接龙。\n"
            "如果能接上，只能输出“继续: <成语>”。\n"
            "如果接不上，只能输出“停止: 接不上了”。\n"
            "不要输出解释，不要输出额外文本。\n"
        ),
        "cli_args.json": "[]\n",
        "env.json": "{}\n",
        "README.txt": (
            f"Folder: {root.name}\n"
            "Agent type: codex\n\n"
            "This example wires two Codex agent nodes together for a Chinese idiom relay game.\n"
            "- system_prompt.txt: node-specific system prompt\n"
            "- cli_args.json: JSON array of extra Codex CLI args\n"
            "- env.json: JSON object of extra environment variables\n"
        ),
    }
    for filename, content in files.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def ensure_demo_agent_directories(working_directory: str) -> dict[str, Path]:
    root = Path(working_directory).resolve()
    player_a_root = default_agent_config_directory(
        working_directory=root,
        name="idiom_player_a",
        folder_name=PLAYER_A_FOLDER,
    )
    player_b_root = default_agent_config_directory(
        working_directory=root,
        name="idiom_player_b",
        folder_name=PLAYER_B_FOLDER,
    )
    for folder, player_label in ((player_a_root, "A"), (player_b_root, "B")):
        folder.mkdir(parents=True, exist_ok=True)
        _ensure_template_files(folder, player_label=player_label)
        reused = build_reused_agent_config(
            agent_type="codex",
            working_directory=folder,
            include_home_defaults=True,
            reuse_fields=("model",),
        )
        write_reused_agent_config(
            agent_type="codex",
            target_directory=folder,
            reused_config=reused,
        )
    return {"player_a": player_a_root, "player_b": player_b_root}


def _build_player_config(*, working_directory: str, name: str, folder_name: str, target: str) -> AgentNodeConfig:
    root = Path(working_directory).resolve()
    agent_root = default_agent_config_directory(working_directory=root, name=name, folder_name=folder_name)
    reused = build_reused_agent_config(
        agent_type="codex",
        working_directory=agent_root,
        include_home_defaults=True,
        reuse_fields=("model",),
    )
    return AgentNodeConfig(
        **apply_reused_agent_config(
        name=name,
        folder_name=folder_name,
        agent_type="codex",
        working_directory=working_directory,
        reused_config=reused,
        system_prompt=_load_text(agent_root / "system_prompt.txt"),
        cli_args=tuple(str(item) for item in _load_optional_json_list(agent_root / "cli_args.json")),
        env={str(k): str(v) for k, v in _load_optional_json(agent_root / "env.json").items()},
        context_window_tokens=200_000,
        persist_runtime_history=False,
        persist_node_mailboxes=True,
        targets=(target,),
        prompt_prefix=(
            "你只能输出单行结果。"
            "合法格式只有“继续: <成语>”或“停止: 接不上了”。"
        ),
        )
    )


def _extract_idiom(text: str) -> str:
    match = CONTINUE_RE.match(text)
    if match:
        return match.group(1)
    items = IDIOM_RE.findall(text)
    return items[-1] if items else ""


def _parse_reply(text: str) -> ParsedIdiomReply:
    continue_match = CONTINUE_RE.match(text)
    if continue_match:
        return ParsedIdiomReply(action="continue", idiom=continue_match.group(1))
    stop_match = STOP_RE.match(text)
    if stop_match:
        reason = stop_match.group(1).strip() or "接不上了"
        return ParsedIdiomReply(action="stop", reason=reason)
    fallback_idiom = _extract_idiom(text)
    if fallback_idiom:
        return ParsedIdiomReply(action="stop", idiom=fallback_idiom, reason="输出格式不符合约定，视为接龙失败")
    return ParsedIdiomReply(action="stop", reason="未能识别有效成语")


def idiom_prompt_builder(
    config: AgentNodeConfig,
    messages: list[InterNodeMessage],
    state: AgentGraphState,
) -> str:
    shared = dict(state.get("shared") or {})
    opponent_message = messages[-1].content if messages else ""
    opponent_idiom = _extract_idiom(opponent_message)
    transcript = list(shared.get("transcript") or [])
    max_rounds = int(shared.get("max_rounds", DEFAULT_MAX_ROUNDS))
    next_round = int(shared.get("rounds_completed", 0)) + 1
    lines = [
        f"你是节点 {config.name}。",
        "你在和另一个 Codex agent 玩成语接龙。",
        f"当前准备执行第 {next_round} / {max_rounds} 回合。",
        f"对方上一条有效成语: {opponent_idiom or '未识别'}",
        "规则:",
        "1. 你的成语首字必须等于对方成语末字。",
        "2. 只允许输出单行。",
        "3. 如果能接上，输出“继续: <成语>”。",
        "4. 如果接不上，输出“停止: 接不上了”。",
        "5. 不要解释，不要重复规则，不要添加其他文字。",
    ]
    if transcript:
        lines.append("最近历史:")
        for item in transcript[-6:]:
            lines.append(f"- {item['speaker']}: {item['text']}")
    return "\n".join(lines)


def planner_node(state: AgentGraphState) -> AgentGraphState:
    shared = dict(state.get("shared") or {})
    seed_idiom = str(shared.get("seed_idiom") or DEFAULT_SEED_IDIOM)
    transcript = [{"speaker": "planner", "text": seed_idiom}]
    message = InterNodeMessage(
        sender="planner",
        recipient="idiom_player_a",
        content=f"继续: {seed_idiom}",
    )
    print(f"[planner] -> idiom_player_a: {message.content}")
    return {
        "mailboxes": {"idiom_player_a": [message.to_dict()]},
        "shared": {
            "transcript": transcript,
            "rounds_completed": 0,
            "game_over": False,
            "winner": "",
            "loser": "",
            "stop_reason": "",
        },
    }


def build_post_turn_node(current_name: str, next_name: str) -> Callable[[AgentGraphState], AgentGraphState]:
    def _post_turn_node(state: AgentGraphState) -> AgentGraphState:
        shared = dict(state.get("shared") or {})
        results = dict(state.get("agent_results") or {})
        result = dict(results.get(current_name, {}))
        final_output = str(result.get("final_output", "")).strip()
        parsed = _parse_reply(final_output)

        transcript = list(shared.get("transcript") or [])
        transcript.append({"speaker": current_name, "text": final_output})
        rounds_completed = int(shared.get("rounds_completed", 0)) + 1
        max_rounds = int(shared.get("max_rounds", DEFAULT_MAX_ROUNDS))

        game_over = False
        stop_reason = ""
        winner = ""
        loser = ""

        if result.get("status") != "completed":
            game_over = True
            stop_reason = str(result.get("error") or result.get("status") or "agent turn failed")
            winner = next_name
            loser = current_name
        elif parsed.action == "stop":
            game_over = True
            stop_reason = parsed.reason
            winner = next_name
            loser = current_name
        elif rounds_completed >= max_rounds:
            game_over = True
            stop_reason = f"达到 {max_rounds} 回合上限"

        print(f"[round {rounds_completed}] {current_name} -> {next_name}: {final_output}")

        return {
            "shared": {
                "transcript": transcript,
                "rounds_completed": rounds_completed,
                "last_speaker": current_name,
                "last_output": final_output,
                "game_over": game_over,
                "winner": winner,
                "loser": loser,
                "stop_reason": stop_reason,
            }
        }

    return _post_turn_node


def route_after_turn(state: AgentGraphState) -> str:
    shared = dict(state.get("shared") or {})
    if shared.get("game_over"):
        return "end"
    last_speaker = str(shared.get("last_speaker") or "")
    if last_speaker == "idiom_player_a":
        return "player_b"
    return "player_a"


def build_logged_agent_node(name: str, node: AgentNode):
    def _logged_agent_node(state: AgentGraphState) -> AgentGraphState:
        mailbox_state = dict(state.get("mailboxes") or {})
        inbound_messages = list(mailbox_state.get(name) or [])
        print(f"[node:start] {name} inbound_count={len(inbound_messages)}")
        for index, payload in enumerate(inbound_messages, start=1):
            message = InterNodeMessage.from_dict(payload)
            print(f"[node:mailbox] {name} [{index}] {message.sender} -> {message.recipient}: {message.content}")
        mailbox_state[name] = []
        if not inbound_messages:
            print(f"[node:skip] {name} no inbound messages")
            return {"agent_results": {name: {"status": "idle", "skipped": True}}}

        print(f"[node:runtime] {name} acquiring runtime")
        runtime = node.get_runtime()
        print(f"[node:runtime] {name} acquired runtime session_id={getattr(runtime, 'session_id', '')!r}")

        inbound = [InterNodeMessage.from_dict(item) for item in inbound_messages]
        prompt = node.prompt_builder(node.config, inbound, state)
        prompt_preview = prompt[:300].replace("\n", "\\n")
        print(f"[node:prompt] {name} prompt_len={len(prompt)} preview={prompt_preview}")

        if node.config.persist_node_mailboxes:
            runtime.workspace.append_jsonl(
                runtime.workspace.inbox_path,
                {"messages": [message.to_dict() for message in inbound]},
            )

        turn_id = ""
        try:
            print(f"[node:turn] {name} sending input")
            turn_id = runtime.send_input(prompt)
            print(f"[node:turn] {name} turn_id={turn_id} sent")
        except Exception as exc:
            print(f"[node:error] {name} send_input failed: {exc}")
            stderr_tail = list(getattr(runtime, "_stderr_tail", []) or [])
            if stderr_tail:
                print(f"[node:stderr] {name} tail:")
                for line in stderr_tail[-10:]:
                    print(f"  {line}")
            raise

        next_index = 0
        last_progress_at = time.time()
        while not runtime.is_output_complete():
            events = runtime.get_output_events(after_index=next_index)
            if events:
                last_progress_at = time.time()
            for event in events:
                next_index = event.index + 1
                content = (event.content or "").strip()
                if len(content) > 200:
                    content = content[:200] + "..."
                print(
                    f"[node:event] {name} type={event.event_type} "
                    f"index={event.index} call_id={event.call_id!r} content={content!r}"
                )
            if time.time() - last_progress_at >= 5.0:
                print(f"[node:wait] {name} still waiting for completion...")
                stderr_tail = list(getattr(runtime, "_stderr_tail", []) or [])
                if stderr_tail:
                    print(f"[node:stderr] {name} tail:")
                    for line in stderr_tail[-5:]:
                        print(f"  {line}")
                last_progress_at = time.time()
            time.sleep(0.2)

        for event in runtime.get_output_events(after_index=next_index):
            next_index = event.index + 1
            content = (event.content or "").strip()
            if len(content) > 200:
                content = content[:200] + "..."
            print(
                f"[node:event] {name} type={event.event_type} "
                f"index={event.index} call_id={event.call_id!r} content={content!r}"
            )

        result = runtime.wait_for_completion(timeout=node.config.turn_timeout_seconds)
        print(
            f"[node:result] {name} status={result.status} "
            f"session_id={result.session_id!r} error={result.error!r}"
        )

        outbound: list[InterNodeMessage] = [
            InterNodeMessage(
                sender=node.config.name,
                recipient=target,
                content=result.final_output,
                metadata={"turn_id": result.turn_id, "session_id": result.session_id, "status": result.status},
            )
            for target in node.config.targets
            if result.final_output
        ]
        for message in outbound:
            mailbox_state.setdefault(message.recipient, []).append(message.to_dict())
            print(f"[node:forward] {name} -> {message.recipient}: {message.content}")
        if outbound and node.config.persist_node_mailboxes:
            runtime.workspace.append_jsonl(
                runtime.workspace.outbox_path,
                {"messages": [message.to_dict() for message in outbound]},
            )

        payload = {
            "mailboxes": mailbox_state,
            "agent_results": {
                node.config.name: {
                    "status": result.status,
                    "session_id": result.session_id,
                    "final_output": result.final_output,
                    "error": result.error,
                    "usage": result.usage.to_dict(),
                    "workspace": str(runtime.workspace.root),
                    "consumed_messages": [message.to_dict() for message in inbound],
                    "forwarded_messages": [message.to_dict() for message in outbound],
                }
            },
        }
        print("[node:end] " f"{name} status={result.status} final_output={result.final_output.strip()!r}")
        return payload

    return _logged_agent_node


def build_demo_graph(registry: AgentRuntimeRegistry, working_directory: str) -> Any:
    from langgraph.graph import END, START, StateGraph

    player_a = AgentNode(
        config=_build_player_config(
            working_directory=working_directory,
            name="idiom_player_a",
            folder_name=PLAYER_A_FOLDER,
            target="idiom_player_b",
        ),
        registry=registry,
        prompt_builder=idiom_prompt_builder,
    )
    player_b = AgentNode(
        config=_build_player_config(
            working_directory=working_directory,
            name="idiom_player_b",
            folder_name=PLAYER_B_FOLDER,
            target="idiom_player_a",
        ),
        registry=registry,
        prompt_builder=idiom_prompt_builder,
    )

    graph = StateGraph(AgentGraphState)
    graph.add_node("planner", planner_node)
    graph.add_node("idiom_player_a", build_logged_agent_node("idiom_player_a", player_a))
    graph.add_node("idiom_player_b", build_logged_agent_node("idiom_player_b", player_b))
    graph.add_node("after_player_a", build_post_turn_node("idiom_player_a", "idiom_player_b"))
    graph.add_node("after_player_b", build_post_turn_node("idiom_player_b", "idiom_player_a"))
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "idiom_player_a")
    graph.add_edge("idiom_player_a", "after_player_a")
    graph.add_edge("idiom_player_b", "after_player_b")
    graph.add_conditional_edges(
        "after_player_a",
        route_after_turn,
        {"player_b": "idiom_player_b", "end": END},
    )
    graph.add_conditional_edges(
        "after_player_b",
        route_after_turn,
        {"player_a": "idiom_player_a", "end": END},
    )
    return graph.compile()


def run_demo(
    *,
    working_directory: str,
    seed_idiom: str,
    max_rounds: int,
) -> dict[str, Any]:
    root = Path(working_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ensure_demo_agent_directories(str(root))
    registry = AgentRuntimeRegistry(base_directory=root / ".workflow" / "agent")
    try:
        app = build_demo_graph(registry, str(root))
        result = app.invoke(
            {
                "shared": {
                    "seed_idiom": seed_idiom,
                    "max_rounds": max_rounds,
                }
            }
        )
        payload = dict(result)
        shared = dict(payload.get("shared") or {})
        return {
            "seed_idiom": seed_idiom,
            "rounds_completed": int(shared.get("rounds_completed", 0) or 0),
            "max_rounds": max_rounds,
            "winner": str(shared.get("winner") or ""),
            "loser": str(shared.get("loser") or ""),
            "stop_reason": str(shared.get("stop_reason") or ""),
            "transcript": list(shared.get("transcript") or []),
            "agent_results": dict(payload.get("agent_results") or {}),
            "mailboxes": dict(payload.get("mailboxes") or {}),
            "shared": shared,
        }
    finally:
        registry.shutdown_all()


def main() -> None:
    working_directory = Path.cwd()
    folders = ensure_demo_agent_directories(working_directory)
    result = run_demo(
        working_directory=working_directory,
        seed_idiom=DEFAULT_SEED_IDIOM,
        max_rounds=DEFAULT_MAX_ROUNDS,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
