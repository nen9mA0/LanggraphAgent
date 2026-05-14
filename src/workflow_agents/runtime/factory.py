from __future__ import annotations

from ..storage import AgentWorkspace
from ..types import AgentNodeConfig
from .base import ManagedAgentRuntime
from .claude import ClaudeCodeRuntime
from .codex import CodexRuntime


def create_agent_runtime(config: AgentNodeConfig, workspace: AgentWorkspace) -> ManagedAgentRuntime:
    """Create the concrete runtime implementation for the configured agent type."""
    if config.agent_type == "claude":
        return ClaudeCodeRuntime(config, workspace)
    if config.agent_type == "codex":
        return CodexRuntime(config, workspace)
    raise ValueError(f"unsupported agent type: {config.agent_type}")
