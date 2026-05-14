from __future__ import annotations

from pathlib import Path
from threading import RLock

from .runtime.factory import create_agent_runtime
from .storage import AgentWorkspaceManager
from .types import AgentNodeConfig


class AgentRuntimeRegistry:
    """Registry that owns runtime instances and their backing workspaces."""

    def __init__(self, base_directory: str | Path | None = None) -> None:
        """Initialize the runtime registry with an optional workspace root."""
        self.workspace_manager = AgentWorkspaceManager(base_directory=base_directory)
        self._lock = RLock()
        self._runtimes: dict[str, object] = {}

    def get_or_create(self, config: AgentNodeConfig):
        """Return an existing runtime for the config or create and start a new one."""
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
        """Shut down every runtime currently owned by the registry."""
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.shutdown()
