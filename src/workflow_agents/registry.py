from __future__ import annotations

from pathlib import Path
from threading import RLock

from .runtime.factory import create_agent_runtime
from .storage import AgentWorkspaceManager
from .types import AgentNodeConfig


class AgentRuntimeRegistry:
    """维护当前的所有Agent Workspace和Agent Runtime"""

    def __init__(self, base_directory: str | Path | None = None) -> None:
        """
        初始化一个RuntimeRegistry，创建WorkspaceManager
        Args:
            [optional] base_directory: 多Agent配置路径
        """
        self.workspace_manager = AgentWorkspaceManager(base_directory=base_directory)
        self._lock = RLock()
        self._runtimes: dict[str, object] = {}

    def get_or_create(self, config: AgentNodeConfig):
        """
        获取当前已有的一个AgentRuntime，或新建一个runtime
        Args:
            config: 要获取的Agent配置
        """
        with self._lock:
            runtime = self._runtimes.get(config.instance_key)
            if runtime is not None:
                return runtime
            workspace = self.workspace_manager.prepare_workspace(config.name, config.folder_name)
            workspace.persist_config(config)
            runtime = create_agent_runtime(config, workspace)
            if config.auto_start:
                runtime.start()
            self._runtimes[config.instance_key] = runtime
            return runtime

    def shutdown_all(self) -> None:
        """关闭当前运行的所有Agent"""
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.shutdown()
