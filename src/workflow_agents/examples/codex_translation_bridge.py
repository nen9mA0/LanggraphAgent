from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


TRANSLATOR_FOLDER = "codex_translation_agent"
DEFAULT_TRANSLATOR_MODEL = "gpt-4o-mini"


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


def _ensure_template_files(root: Path) -> None:
    files: dict[str, str] = {
        "system_prompt.txt": (
            "You are the English-speaking Codex node behind a translation bridge.\n"
            "You always receive English input and must answer in English only.\n"
            "Keep the answer concise and useful.\n"
        ),
        "cli_args.json": "[]\n",
        "env.json": "{}\n",
        "README.txt": (
            f"Folder: {root.name}\n"
            "Agent type: codex\n\n"
            "This example accepts Chinese user input, translates it to English with a normal LLM node,\n"
            "sends the English text into a Codex agent node, then translates the English answer back to Chinese.\n"
        ),
    }
    for filename, content in files.items():
        path = root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def ensure_demo_agent_directories(working_directory: str) -> Path:
    root = Path(working_directory).resolve()
    agent_root = default_agent_config_directory(
        working_directory=root,
        name="english_codex_agent",
        folder_name=TRANSLATOR_FOLDER,
    )
    agent_root.mkdir(parents=True, exist_ok=True)
    _ensure_template_files(agent_root)
    reused = build_reused_agent_config(
        agent_type="codex",
        working_directory=agent_root,
        include_home_defaults=True,
        reuse_fields=("model",),
    )
    write_reused_agent_config(
        agent_type="codex",
        target_directory=agent_root,
        reused_config=reused,
    )
    return agent_root


def _build_agent_config(*, working_directory: str) -> AgentNodeConfig:
    root = Path(working_directory).resolve()
    agent_root = default_agent_config_directory(
        working_directory=root,
        name="english_codex_agent",
        folder_name=TRANSLATOR_FOLDER,
    )
    reused = build_reused_agent_config(
        agent_type="codex",
        working_directory=agent_root,
        include_home_defaults=True,
        reuse_fields=("model",),
    )
    return AgentNodeConfig(
        **apply_reused_agent_config(
            reused_config=reused,
            name="english_codex_agent",
            folder_name=TRANSLATOR_FOLDER,
            agent_type="codex",
            executable_path="codex",
            working_directory=working_directory,
            system_prompt=_load_text(agent_root / "system_prompt.txt"),
            cli_args=tuple(str(item) for item in _load_optional_json_list(agent_root / "cli_args.json")),
            env={str(k): str(v) for k, v in _load_optional_json(agent_root / "env.json").items()},
            context_window_tokens=200_000,
            persist_runtime_history=False,
            persist_node_mailboxes=True,
            targets=("translator_out",),
            prompt_prefix="The upstream translator already converted the user request to English. Answer in English only.",
        )
    )


def english_agent_prompt_builder(
    config: AgentNodeConfig,
    messages: list[InterNodeMessage],
    state: AgentGraphState,
) -> str:
    user_request = messages[-1].content.strip() if messages else ""
    lines = [
        f"Node: {config.name}",
        "You are the Codex node in a translation bridge.",
        "The user request below is already translated into English.",
        "Answer in English only. Do not mention the translator nodes.",
        "",
        "User request:",
        user_request,
    ]
    return "\n".join(lines)


@dataclass(slots=True)
class OpenAITranslator:
    model: str = DEFAULT_TRANSLATOR_MODEL
    api_key_env: str = "OPENAI_API_KEY"
    base_url_env: str = "OPENAI_BASE_URL"
    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError("The `openai` package is required for the translator node example.") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing {self.api_key_env} for the translator node example.")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        base_url = os.getenv(self.base_url_env)
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)

    def _extract_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", "")
        if output_text:
            return str(output_text).strip()

        output = getattr(response, "output", None)
        if output:
            texts: list[str] = []
            for item in output:
                for content in getattr(item, "content", None) or []:
                    text_value = getattr(content, "text", None)
                    if text_value:
                        texts.append(str(text_value))
            if texts:
                return "\n".join(texts).strip()

        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", "")
            if content:
                return str(content).strip()
        raise RuntimeError("Unable to extract text from translator response.")

    def translate(self, *, text: str, source_language: str, target_language: str) -> str:
        instructions = (
            f"Translate the user content from {source_language} to {target_language}. "
            "Return only the translation without explanation."
        )

        responses_api = getattr(self._client, "responses", None)
        if responses_api is not None and hasattr(responses_api, "create"):
            response = responses_api.create(
                model=self.model,
                input=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": text},
                ],
            )
            return self._extract_text(response)

        chat_api = getattr(getattr(self._client, "chat", None), "completions", None)
        if chat_api is not None and hasattr(chat_api, "create"):
            response = chat_api.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": text},
                ],
            )
            return self._extract_text(response)

        raise RuntimeError("The configured OpenAI client does not expose a supported text generation API.")


def build_translator_in_node(translator: OpenAITranslator):
    def translator_in_node(state: AgentGraphState) -> AgentGraphState:
        shared = dict(state.get("shared") or {})
        user_input = str(shared.get("user_input_zh", "")).strip()
        if not user_input:
            return {
                "agent_results": {
                    "translator_in": {
                        "stage": "idle",
                        "skipped": True,
                    }
                }
            }

        translated = translator.translate(
            text=user_input,
            source_language="Chinese",
            target_language="English",
        )
        print(f"[llm translated to english] {translated}")
        outbound = InterNodeMessage(
            sender="translator_in",
            recipient="english_codex_agent",
            content=translated,
        )
        return {
            "mailboxes": {"english_codex_agent": [outbound.to_dict()]},
            "shared": {"translated_input_en": translated},
            "agent_results": {
                "translator_in": {
                    "stage": "user_to_agent",
                    "source_text": user_input,
                    "translated_text": translated,
                }
            },
        }

    return translator_in_node


def build_translator_out_node(translator: OpenAITranslator):
    def translator_out_node(state: AgentGraphState) -> AgentGraphState:
        mailbox_state = {key: list(value) for key, value in (state.get("mailboxes") or {}).items()}
        inbound = [InterNodeMessage.from_dict(item) for item in mailbox_state.get("translator_out", [])]
        mailbox_state["translator_out"] = []
        if not inbound:
            return {
                "mailboxes": mailbox_state,
                "agent_results": {
                    "translator_out": {
                        "stage": "idle",
                        "skipped": True,
                    }
                },
            }

        agent_text = inbound[-1].content.strip()
        print(f"[agent node output before translation] {agent_text}")
        translated = translator.translate(
            text=agent_text,
            source_language="English",
            target_language="Chinese",
        )
        return {
            "mailboxes": mailbox_state,
            "shared": {
                "agent_output_en": agent_text,
                "final_output_zh": translated,
            },
            "agent_results": {
                "translator_out": {
                    "stage": "agent_to_user",
                    "source_text": agent_text,
                    "translated_text": translated,
                }
            },
        }

    return translator_out_node


def build_demo_graph(
    registry: AgentRuntimeRegistry,
    working_directory: str,
    *,
    translator_model: str = DEFAULT_TRANSLATOR_MODEL,
) -> Any:
    from langgraph.graph import END, START, StateGraph

    translator = OpenAITranslator(model=translator_model)
    translator_in = build_translator_in_node(translator)
    translator_out = build_translator_out_node(translator)
    agent = AgentNode(
        config=_build_agent_config(working_directory=working_directory),
        registry=registry,
        prompt_builder=english_agent_prompt_builder,
    )

    graph = StateGraph(AgentGraphState)
    graph.add_node("translator_in", translator_in)
    graph.add_node("english_codex_agent", agent)
    graph.add_node("translator_out", translator_out)
    graph.add_edge(START, "translator_in")
    graph.add_edge("translator_in", "english_codex_agent")
    graph.add_edge("english_codex_agent", "translator_out")
    graph.add_edge("translator_out", END)
    return graph.compile()


def run_demo(
    *,
    working_directory: str,
    user_input_zh: str,
    translator_model: str = DEFAULT_TRANSLATOR_MODEL,
) -> dict[str, Any]:
    root = Path(working_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    ensure_demo_agent_directories(str(root))
    registry = AgentRuntimeRegistry(base_directory=root / ".workflow" / "agent")
    try:
        app = build_demo_graph(registry, str(root), translator_model=translator_model)
        result = app.invoke({"shared": {"user_input_zh": user_input_zh}})
        payload = dict(result)
        shared = dict(payload.get("shared") or {})
        return {
            "user_input_zh": user_input_zh,
            "translated_input_en": str(shared.get("translated_input_en") or ""),
            "agent_output_en": str(shared.get("agent_output_en") or ""),
            "final_output_zh": str(shared.get("final_output_zh") or ""),
            "agent_results": dict(payload.get("agent_results") or {}),
            "mailboxes": dict(payload.get("mailboxes") or {}),
            "shared": shared,
        }
    finally:
        registry.shutdown_all()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a translator LLM node <-> Codex agent bridge example.")
    parser.add_argument(
        "--working-directory",
        default=str(Path.cwd()),
        help="Workspace shared by the translator node and the Codex node. Default: current directory.",
    )
    parser.add_argument(
        "--user-input-zh",
        default="请用三句话解释为什么长期运行的 agent node 在工作流里有用。",
        help="Chinese user input that will be translated to English before reaching the Codex node.",
    )
    parser.add_argument(
        "--translator-model",
        default=DEFAULT_TRANSLATOR_MODEL,
        help="Model name used by the translator LLM node.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only create the .workflow/agent folder and template files, then exit.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    folder = ensure_demo_agent_directories(args.working_directory)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "prepared": True,
                    "agent_folder": str(folder),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    result = run_demo(
        working_directory=args.working_directory,
        user_input_zh=args.user_input_zh,
        translator_model=args.translator_model,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
