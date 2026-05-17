from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from workflow_agents.runtime.claude import ClaudeCodeRuntime
from workflow_agents.runtime.codex import CodexRuntime
from workflow_agents.storage import AgentWorkspace
from workflow_agents.types import AgentNodeConfig


def integration_enabled() -> bool:
    """Return whether real CLI integration tests are enabled."""
    return os.environ.get("WORKFLOW_AGENTS_RUN_REAL_CLI_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


class RuntimeCliAvailabilityTestCase(unittest.TestCase):
    """Real CLI smoke tests for Claude and Codex runtimes."""

    @classmethod
    def setUpClass(cls) -> None:
        if not integration_enabled():
            raise unittest.SkipTest("set WORKFLOW_AGENTS_RUN_REAL_CLI_TESTS=1 to run real CLI availability tests")

    def test_claude_version_command_is_available(self) -> None:
        executable = shutil.which("claude")
        if not executable:
            self.skipTest("claude executable is not available on PATH")

        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("claude", result.stdout.lower())

    def test_codex_version_command_is_available(self) -> None:
        executable = shutil.which("codex")
        if not executable:
            self.skipTest("codex executable is not available on PATH")

        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("codex", result.stdout.lower())

    def test_claude_runtime_start_smoke(self) -> None:
        executable = shutil.which("claude")
        if not executable:
            self.skipTest("claude executable is not available on PATH")

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / ".workflow" / "agent" / "claude_runtime_smoke"
            workspace = AgentWorkspace(node_name="claude_runtime_smoke", folder_name="claude_runtime_smoke", root=workspace_root)
            config = AgentNodeConfig(
                name="claude_runtime_smoke",
                folder_name="claude_runtime_smoke",
                agent_type="claude",
                executable_path=executable,
                working_directory=temp_dir,
                auto_start=False,
            )
            runtime = ClaudeCodeRuntime(config, workspace)
            runtime.start()
            runtime.shutdown()

    def test_codex_runtime_start_and_shutdown_smoke(self) -> None:
        executable = shutil.which("codex")
        if not executable:
            self.skipTest("codex executable is not available on PATH")

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / ".workflow" / "agent" / "codex_runtime_smoke"
            workspace = AgentWorkspace(node_name="codex_runtime_smoke", folder_name="codex_runtime_smoke", root=workspace_root)
            config = AgentNodeConfig(
                name="codex_runtime_smoke",
                folder_name="codex_runtime_smoke",
                agent_type="codex",
                executable_path=executable,
                working_directory=temp_dir,
                auto_start=False,
                startup_timeout_seconds=30.0,
            )
            runtime = CodexRuntime(config, workspace)
            try:
                runtime.start()
                self.assertTrue(runtime.session_id)
            finally:
                runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
