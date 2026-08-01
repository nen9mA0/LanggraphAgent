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
from workflow_agents.runtime.claude_sdk import ClaudeSDKRuntime
from workflow_agents.runtime.codex import CodexRuntime
from workflow_agents.runtime.codex_sdk import CodexSDKRuntime
from workflow_agents.storage import AgentWorkspace
from workflow_agents.types import AgentNodeConfig


def integration_enabled() -> bool:
    """Return whether real CLI integration tests are enabled."""
    return os.environ.get("WORKFLOW_AGENTS_RUN_REAL_CLI_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


def claude_sdk_integration_enabled() -> bool:
    """Return whether real Claude SDK integration tests are enabled."""
    return os.environ.get("WORKFLOW_AGENTS_RUN_REAL_CLAUDE_SDK_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


class RuntimeCliAvailabilityTestCase(unittest.TestCase):
    """Real CLI smoke tests for Claude and Codex runtimes."""

    @classmethod
    def setUpClass(cls) -> None:
        if not integration_enabled():
            raise unittest.SkipTest("set WORKFLOW_AGENTS_RUN_REAL_CLI_TESTS=1 to run real CLI availability tests")

    # 检查命令行是否可以运行claude --version
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

    # 检查命令行是否可以运行codex --version
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
            workspace = AgentWorkspace(node_name="claude_runtime_smoke", root=workspace_root)
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
            workspace_root = Path(temp_dir) / ".workflow" / "agent"
            workspace = AgentWorkspace(node_name="codex_runtime_smoke", root=workspace_root)
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


class ClaudeSDKRuntimeIntegrationTestCase(unittest.TestCase):
    """Opt-in real integration tests for the Claude SDK runtime."""

    @classmethod
    def setUpClass(cls) -> None:
        if not claude_sdk_integration_enabled():
            raise unittest.SkipTest(
                "set WORKFLOW_AGENTS_RUN_REAL_CLAUDE_SDK_TESTS=1 to run real Claude SDK integration tests"
            )

    def test_claude_sdk_runtime_start_and_run_turn_smoke(self) -> None:
        python_executable = os.environ.get("WORKFLOW_AGENTS_CLAUDE_SDK_PYTHON", "").strip()
        if not python_executable:
            self.skipTest("set WORKFLOW_AGENTS_CLAUDE_SDK_PYTHON to the Python interpreter that can import claude_agent_sdk")
        if not Path(python_executable).exists():
            self.skipTest(f"configured WORKFLOW_AGENTS_CLAUDE_SDK_PYTHON does not exist: {python_executable}")

        cli_path = os.environ.get("WORKFLOW_AGENTS_CLAUDE_CLI_PATH", "").strip()
        if not cli_path:
            cli_path = shutil.which("claude") or ""
        if not cli_path:
            self.skipTest("set WORKFLOW_AGENTS_CLAUDE_CLI_PATH or ensure claude is on PATH")

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / ".workflow" / "agent" / "claude_sdk_runtime_smoke"
            workspace = AgentWorkspace(node_name="claude_sdk_runtime_smoke", folder_name="claude_sdk_runtime_smoke", root=workspace_root)
            config = AgentNodeConfig(
                name="claude_sdk_runtime_smoke",
                folder_name="claude_sdk_runtime_smoke",
                agent_type="claude_sdk",
                executable_path=python_executable,
                working_directory=temp_dir,
                auto_start=False,
                startup_timeout_seconds=30.0,
                turn_timeout_seconds=120.0,
                runtime_options={
                    "python_executable": python_executable,
                    "sdk_module": os.environ.get("WORKFLOW_AGENTS_CLAUDE_SDK_MODULE", "").strip() or "claude_agent_sdk",
                    "cli_path": cli_path,
                    "client_options": {},
                },
            )
            runtime = ClaudeSDKRuntime(config, workspace)
            try:
                runtime.start()
                result = runtime.run_turn("Reply with the single word OK.")
                self.assertEqual(result.status, "completed")
                self.assertTrue(result.final_output.strip())
                self.assertTrue(runtime.session_id)
            finally:
                runtime.shutdown()

class ClaudeSDKRuntimeErrorPathTestCase(unittest.TestCase):
    """Always-on tests for Claude SDK runtime failure paths."""

    def test_claude_sdk_runtime_missing_sdk_reports_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / ".workflow" / "agent" / "claude_sdk_runtime_smoke"
            workspace = AgentWorkspace(
                node_name="claude_sdk_runtime_smoke",
                folder_name="claude_sdk_runtime_smoke",
                root=workspace_root,
            )
            config = AgentNodeConfig(
                name="claude_sdk_runtime_smoke",
                folder_name="claude_sdk_runtime_smoke",
                agent_type="claude_sdk",
                executable_path=sys.executable,
                working_directory=temp_dir,
                auto_start=False,
                startup_timeout_seconds=5.0,
                runtime_options={
                    "python_executable": sys.executable,
                    "sdk_module": "definitely_missing_claude_sdk_module",
                },
            )
            runtime = ClaudeSDKRuntime(config, workspace)
            try:
                with self.assertRaises(RuntimeError) as exc:
                    runtime.start()
                self.assertIn("definitely_missing_claude_sdk_module", str(exc.exception))
            finally:
                runtime.shutdown()


class CodexSDKRuntimeErrorPathTestCase(unittest.TestCase):
    """Always-on tests for Codex SDK runtime failure paths."""

    def test_codex_sdk_runtime_missing_sdk_reports_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir) / ".workflow" / "agent" / "codex_sdk_runtime_smoke"
            workspace = AgentWorkspace(
                node_name="codex_sdk_runtime_smoke",
                folder_name="codex_sdk_runtime_smoke",
                root=workspace_root,
            )
            config = AgentNodeConfig(
                name="codex_sdk_runtime_smoke",
                folder_name="codex_sdk_runtime_smoke",
                agent_type="codex_sdk",
                executable_path=sys.executable,
                working_directory=temp_dir,
                auto_start=False,
                startup_timeout_seconds=5.0,
                runtime_options={
                    "python_executable": sys.executable,
                    "sdk_module": "definitely_missing_codex_sdk_module",
                },
            )
            runtime = CodexSDKRuntime(config, workspace)
            try:
                with self.assertRaises(RuntimeError) as exc:
                    runtime.start()
                self.assertIn("definitely_missing_codex_sdk_module", str(exc.exception))
            finally:
                runtime.shutdown()


if __name__ == "__main__":
    unittest.main()
