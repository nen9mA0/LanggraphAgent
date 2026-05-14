from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from .types import AgentNodeConfig


def slugify_name(value: str) -> str:
    """Convert a node name into a filesystem-safe folder name."""
    text = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "agent"


@dataclass(slots=True)
class AgentWorkspace:
    """Filesystem paths and helpers for a single agent node workspace."""

    node_name: str
    folder_name: str
    root: Path

    @property
    def config_path(self) -> Path:
        """Return the path used to persist agent configuration."""
        return self.root / "config.json"

    @property
    def runtime_path(self) -> Path:
        """Return the path used to persist runtime session state."""
        return self.root / "runtime.json"

    @property
    def history_path(self) -> Path:
        """Return the path used to append raw turn and event history."""
        return self.root / "history.jsonl"

    @property
    def inbox_path(self) -> Path:
        """Return the path used to log inbound mailbox messages."""
        return self.root / "inbox.jsonl"

    @property
    def outbox_path(self) -> Path:
        """Return the path used to log outbound mailbox messages."""
        return self.root / "outbox.jsonl"

    def ensure(self) -> None:
        """Create the workspace directory if it does not already exist."""
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Write a JSON document under the workspace."""
        self.ensure()
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def read_json(self, path: Path) -> dict[str, Any]:
        """Read a JSON document, returning an empty object when missing."""
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        """Append a single JSON line record under the workspace."""
        self.ensure()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True))
            handle.write("\n")

    def persist_config(self, config: AgentNodeConfig) -> None:
        """Persist the current agent configuration to disk."""
        self.write_json(self.config_path, config.to_persistable_dict())

    def load_runtime_state(self) -> dict[str, Any]:
        """Load persisted runtime session state from disk."""
        return self.read_json(self.runtime_path)

    def save_runtime_state(self, payload: dict[str, Any]) -> None:
        """Persist runtime session state to disk."""
        self.write_json(self.runtime_path, payload)


class AgentWorkspaceManager:
    """Allocate and reuse workspace folders for agent nodes."""

    def __init__(self, base_directory: str | Path | None = None) -> None:
        """Initialize the workspace manager under the given base directory."""
        if base_directory is None:
            base_directory = Path.cwd() / ".workflow" / "agent"
        self.base_directory = Path(base_directory).resolve()
        self.base_directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._allocated: set[Path] = set()

    def prepare_workspace(self, node_name: str, preferred_name: str | None = None) -> AgentWorkspace:
        """Return a workspace for a node, creating a unique folder when needed."""
        base_name = slugify_name(preferred_name or node_name)
        with self._lock:
            if preferred_name:
                root = self.base_directory / base_name
                workspace = AgentWorkspace(node_name=node_name, folder_name=base_name, root=root)
                workspace.ensure()
                self._allocated.add(root)
                return workspace
            index = 0
            while True:
                folder_name = base_name if index == 0 else f"{base_name}_{index}"
                root = self.base_directory / folder_name
                if root not in self._allocated and not root.exists():
                    workspace = AgentWorkspace(node_name=node_name, folder_name=folder_name, root=root)
                    workspace.ensure()
                    self._allocated.add(root)
                    return workspace
                index += 1
