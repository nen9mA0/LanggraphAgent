from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .registry import AgentRuntimeRegistry
from .state import AgentGraphState
from .types import AgentNodeConfig, InterNodeMessage, TurnResult

PromptBuilder = Callable[[AgentNodeConfig, Sequence[InterNodeMessage], Mapping[str, Any]], str]


def default_prompt_builder(
    config: AgentNodeConfig,
    messages: Sequence[InterNodeMessage],
    state: Mapping[str, Any],
) -> str:
    """Build the default node-orchestration prompt passed into an agent runtime."""
    lines = [
        f"Node: {config.name}",
        "You are operating as a workflow node inside a multi-agent graph.",
        "Process only the external node-to-node messages below.",
        "Your final answer will be sent as the message body to downstream nodes.",
        "Do not include internal tool execution details unless explicitly asked.",
    ]
    if config.targets:
        lines.append(f"Allowed downstream recipients: {', '.join(config.targets)}")
    if config.prompt_prefix:
        lines.append(config.prompt_prefix)
    if not messages:
        lines.append("No inbound messages.")
    for index, message in enumerate(messages, start=1):
        lines.append(
            f"[{index}] from={message.sender} to={message.recipient} at={message.created_at}\n{message.content}"
        )
    return "\n\n".join(lines)


@dataclass(slots=True)
class AgentNode:
    """
    在Langgraph中Agent作为Node的包装器
    Args:
        config: Agent配置
        [optional] registry: AgentRuntimeRegistry，用于维护Agent配置和Agent运行时
        [optional] prompt_builder: 用于加工初始化prompt的函数
    """

    config: AgentNodeConfig
    registry: AgentRuntimeRegistry | None = None
    prompt_builder: PromptBuilder = default_prompt_builder

    def __post_init__(self) -> None:
        """Attach a registry when one is not provided explicitly."""
        if self.registry is None:
            self.registry = AgentRuntimeRegistry()

    def get_runtime(self):
        """Return the lazily created runtime for this node configuration."""
        assert self.registry is not None
        return self.registry.get_or_create(self.config)

    def invoke_direct(self, prompt: str) -> TurnResult:
        """Run a prompt directly against the managed runtime outside graph execution."""
        return self.get_runtime().run_turn(prompt)

    def __call__(self, state: AgentGraphState) -> AgentGraphState:
        """Consume mailbox messages, run the agent turn, and emit updated graph state."""
        mailbox_state = {key: list(value) for key, value in (state.get("mailboxes") or {}).items()}
        inbound = [InterNodeMessage.from_dict(item) for item in mailbox_state.get(self.config.name, [])]
        mailbox_state[self.config.name] = []
        if not inbound:
            return {"agent_results": {self.config.name: {"status": "idle", "skipped": True}}}

        runtime = self.get_runtime()
        if self.config.persist_node_mailboxes:
            runtime.workspace.append_jsonl(
                runtime.workspace.inbox_path,
                {"messages": [message.to_dict() for message in inbound]},
            )
        prompt = self.prompt_builder(self.config, inbound, state)
        result = runtime.run_turn(prompt, timeout=self.config.turn_timeout_seconds)

        outbound: list[InterNodeMessage] = [
            InterNodeMessage(
                sender=self.config.name,
                recipient=target,
                content=result.final_output,
                metadata={"turn_id": result.turn_id, "session_id": result.session_id, "status": result.status},
            )
            for target in self.config.targets
            if result.final_output
        ]
        for message in outbound:
            mailbox_state.setdefault(message.recipient, []).append(message.to_dict())
        if outbound and self.config.persist_node_mailboxes:
            runtime.workspace.append_jsonl(
                runtime.workspace.outbox_path,
                {"messages": [message.to_dict() for message in outbound]},
            )

        return {
            "mailboxes": mailbox_state,
            "agent_results": {
                self.config.name: {
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


def build_agent_node(
    config: AgentNodeConfig,
    *,
    registry: AgentRuntimeRegistry | None = None,
    prompt_builder: PromptBuilder = default_prompt_builder,
) -> AgentNode:
    """
    创建一个AgentNode的Helper函数
    """
    return AgentNode(config=config, registry=registry, prompt_builder=prompt_builder)
