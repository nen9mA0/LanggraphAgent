from __future__ import annotations

from ..storage import AgentWorkspace
from ..types import AgentNodeConfig
from .base import ManagedAgentRuntime
from .claude import ClaudeCodeRuntime
from .claude_sdk import ClaudeSDKRuntime
from .codex import CodexRuntime
from .codex_sdk import CodexSDKRuntime


def create_agent_runtime(config: AgentNodeConfig, workspace: AgentWorkspace) -> ManagedAgentRuntime:
    """根据Agent类型创建对应的runtime"""
    if config.agent_type == "claude":
        return ClaudeCodeRuntime(config, workspace)
    if config.agent_type == "claude_sdk":
        return ClaudeSDKRuntime(config, workspace)
    if config.agent_type == "codex":
        return CodexRuntime(config, workspace)
    if config.agent_type == "codex_sdk":
        return CodexSDKRuntime(config, workspace)
    raise ValueError(f"unsupported agent type: {config.agent_type}")
