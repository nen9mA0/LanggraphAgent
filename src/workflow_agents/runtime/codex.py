from __future__ import annotations

import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from ..types import AgentNodeConfig, TokenUsageSnapshot
from .base import ManagedAgentRuntime
from .codex_schema.ClientNotification import ClientNotification, ClientNotification1
from .codex_schema.ClientRequest import (
    ClientRequest1,
    ClientRequest2,
    ClientRequest3,
    ClientRequest48,
    ClientRequest49,
    InitializeParams,
    ThreadResumeParams,
    ThreadStartParams,
    TurnStartParams,
)
from .codex_schema.CommandExecutionRequestApprovalParams import CommandExecutionRequestApprovalParams
from .codex_schema.CommandExecutionRequestApprovalResponse import CommandExecutionRequestApprovalResponse
from .codex_schema.FileChangeRequestApprovalParams import FileChangeRequestApprovalParams
from .codex_schema.FileChangeRequestApprovalResponse import FileChangeRequestApprovalResponse
from .codex_schema.McpServerElicitationRequestResponse import McpServerElicitationRequestResponse
from .codex_schema.McpServerElicitationRequestParams import McpServerElicitationRequestParams
from .codex_schema.ClientRequest import TurnInterruptParams


_SCHEMA_DIR = Path(__file__).resolve().parent / "codex_schema"


def _load_schema_module(filename: str, module_name: str):
    """Load a generated schema module whose filename is not a valid package name."""
    spec = importlib.util.spec_from_file_location(module_name, _SCHEMA_DIR / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load schema module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_PROTO = _load_schema_module(
    "codex_app_server_protocol.schemas.py",
    "workflow_agents.runtime.codex_schema._codex_app_server_protocol_schemas",
)
_PROTO_V2 = _load_schema_module(
    "codex_app_server_protocol.v2.schemas.py",
    "workflow_agents.runtime.codex_schema._codex_app_server_protocol_v2_schemas",
)

JSONRPCMessage = _PROTO.JSONRPCMessage
JSONRPCRequest = _PROTO.JSONRPCRequest
JSONRPCNotification = _PROTO.JSONRPCNotification
JSONRPCResponse = _PROTO.JSONRPCResponse
JSONRPCError = _PROTO.JSONRPCError
ToolRequestUserInputParams = _PROTO.ToolRequestUserInputParams
ToolRequestUserInputResponse = _PROTO.ToolRequestUserInputResponse
GrantedPermissionProfile = _PROTO.GrantedPermissionProfile
PermissionsRequestApprovalResponse = _PROTO.PermissionsRequestApprovalResponse
TurnStartedNotification = _PROTO.TurnStartedNotification
TurnCompletedNotification = _PROTO.TurnCompletedNotification
TurnDiffUpdatedNotification = _PROTO.TurnDiffUpdatedNotification
TurnPlanUpdatedNotification = _PROTO.TurnPlanUpdatedNotification
ItemStartedNotification = _PROTO.ItemStartedNotification
ItemCompletedNotification = _PROTO.ItemCompletedNotification
AgentMessageDeltaNotification = _PROTO_V2.AgentMessageDeltaNotification
ReasoningTextDeltaNotification = _PROTO_V2.ReasoningTextDeltaNotification
CommandExecutionOutputDeltaNotification = _PROTO_V2.CommandExecutionOutputDeltaNotification
FileChangeOutputDeltaNotification = _PROTO_V2.FileChangeOutputDeltaNotification

_JSONRPC_MESSAGE_ADAPTER = TypeAdapter(JSONRPCMessage)
_CLIENT_REQUEST_ADAPTERS = {
    "initialize": TypeAdapter(ClientRequest1),
    "thread/start": TypeAdapter(ClientRequest2),
    "thread/resume": TypeAdapter(ClientRequest3),
    "turn/start": TypeAdapter(ClientRequest48),
    "turn/interrupt": TypeAdapter(ClientRequest49),
}
_CLIENT_NOTIFICATION_ADAPTER = TypeAdapter(ClientNotification1)


class CodexRuntime(ManagedAgentRuntime):
    """Managed runtime that talks to Codex through its JSON-RPC app-server."""

    def __init__(self, config: AgentNodeConfig, workspace) -> None:
        """Initialize Codex runtime process, request tracking, and turn state."""
        super().__init__(config, workspace)
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=50)
        self._request_id = 0
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._rpc_lock = threading.RLock()
        self._thread_id = self.session_id
        self._active_turn_id = ""
        self._active_remote_turn_id = ""
        self._item_text_buffers: dict[str, str] = {}

    def _start_impl(self) -> None:
        """
        启动Agent，命令为codex app-server --listen stdio://
        * 启动子进程并配置标准输入输出线程
        * 发送initialize request
        * 发送initialized notify
        * 若当前runtime有session_id则使用thread/resume继续会话
        * 否则用thread/start启动新会话，并保存session_id
        """
        executable = self._resolve_executable()
        codex_home = self._prepare_codex_home()
        process = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://", *self._config_override_args(), *self.config.cli_args],
            cwd=str(self.config.normalized_working_directory()),
            env={**os.environ, **self.config.env, "CODEX_HOME": str(codex_home)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._process = process
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

        self._rpc_request(
            "initialize",
            InitializeParams(
                clientInfo={"name": "workflow_agents", "version": "0.1.0"},
                capabilities={"experimentalApi": True},
            ),
            timeout=self.config.startup_timeout_seconds,
        )
        self._rpc_notify("initialized", ClientNotification1(method="initialized"))

        if self._thread_id:
            try:
                response = self._rpc_request(
                    "thread/resume",
                    ThreadResumeParams(
                        threadId=self._thread_id,
                        cwd=str(self.config.normalized_working_directory()),
                        model=self.config.model or None,
                        developerInstructions=self.config.system_prompt or None,
                    ),
                    timeout=self.config.startup_timeout_seconds,
                )
                self._thread_id = self._extract_thread_id(response) or self._thread_id
            except Exception:
                self._thread_id = ""

        if not self._thread_id:
            response = self._rpc_request(
                "thread/start",
                ThreadStartParams(
                    model=self.config.model or None,
                    cwd=str(self.config.normalized_working_directory()),
                    developerInstructions=self.config.system_prompt or None,
                ),
                timeout=self.config.startup_timeout_seconds,
            )
            self._thread_id = self._extract_thread_id(response)
            if not self._thread_id:
                raise RuntimeError("codex thread/start returned no thread id")
            self._set_session_id(self._thread_id)

    def _resolve_executable(self) -> str:
        """Return the Codex executable path after validating availability."""
        if self.config.executable_path:
            executable = self.config.executable_path
        else:
            executable = shutil.which("codex")
            if not executable:
                raise ValueError("codex executable is not available on PATH")
        if shutil.which(executable) is None and not Path(executable).exists():
            raise FileNotFoundError(f"codex executable not found: {executable}")
        return executable

    def _send_input_impl(self, prompt: str, turn_id: str) -> None:
        """发送新的turn/start请求"""
        if not self._thread_id:
            raise RuntimeError("codex thread not initialized")
        self._active_turn_id = turn_id
        self._active_remote_turn_id = ""
        self._item_text_buffers.clear()
        response = self._rpc_request(
            "turn/start",
            TurnStartParams(
                threadId=self._thread_id,
                input=[{"type": "text", "text": prompt}],
            ),
            timeout=self.config.startup_timeout_seconds,
        )
        self._active_remote_turn_id = self._extract_turn_id(response)

    def _rpc_notify(self, method: str, params: Any | None = None) -> None:
        """向codex发送一个JSON-RPC notification"""
        self._write_rpc({"jsonrpc": "2.0", "method": method, "params": self._model_dump(params) if params is not None else {}})

    def _rpc_request(self, method: str, params: Any, timeout: float) -> dict[str, Any]:
        """向codex server发送一个JSONRPC request并且等待回应"""
        with self._rpc_lock:
            self._request_id += 1
            request_id = self._request_id
            response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = response_queue
        self._write_rpc({"jsonrpc": "2.0", "id": request_id, "method": method, "params": self._model_dump(params)})
        try:
            payload = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self._rpc_lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"codex request timed out: {method}") from exc
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload.get("result", {})

    def _write_rpc(self, payload: dict[str, Any]) -> None:
        """从标准输入向codex写入一段JSONRPC请求"""
        if self._process is None or self._process.stdin is None or self._process.stdin.closed:
            raise RuntimeError("codex process is not running")
        self._process.stdin.write(json.dumps(payload, ensure_ascii=True))
        self._process.stdin.write("\n")
        self._process.stdin.flush()

    def _model_dump(self, value: Any) -> Any:
        """Convert generated Pydantic models into JSON-serializable data."""
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    def _validate_jsonrpc_message(self, payload: Any) -> JSONRPCMessage:
        """Validate an incoming payload against the generated JSON-RPC union."""
        return _JSONRPC_MESSAGE_ADAPTER.validate_python(payload)

    def _reader_loop(self) -> None:
        """
        读取输出行，并根据输出内容处理
        * 包含id和result/error  _handle_response
        * 包含id和method  _handle_server_request
        * 包含method  _handle_notification
        """
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                text = line.strip()
                if not text:
                    continue
                payload = self._validate_jsonrpc_message(json.loads(text))
                if isinstance(payload.root, JSONRPCResponse):
                    self._handle_response(payload.root)
                elif isinstance(payload.root, JSONRPCError):
                    self._handle_error(payload.root)
                elif isinstance(payload.root, JSONRPCRequest):
                    self._handle_server_request(payload.root)
                elif isinstance(payload.root, JSONRPCNotification):
                    self._handle_notification(payload.root)
        finally:
            with self._rpc_lock:
                for response_queue in self._pending.values():
                    response_queue.put({"error": "codex process exited"})
                self._pending.clear()

    def _stderr_loop(self) -> None:
        """读取stderr行"""
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            text = line.rstrip()
            if text:
                self._stderr_tail.append(text)

    def _handle_response(self, payload: JSONRPCResponse) -> None:
        """处理普通输出"""
        request_id = int(payload.id.root)
        with self._rpc_lock:
            response_queue = self._pending.pop(request_id, None)
        if response_queue is None:
            return
        response_queue.put({"result": self._model_dump(payload.result)})

    def _handle_error(self, payload: JSONRPCError) -> None:
        """Handle a JSON-RPC error object."""
        request_id = int(payload.id.root)
        with self._rpc_lock:
            response_queue = self._pending.pop(request_id, None)
        if response_queue is None:
            return
        response_queue.put({"error": payload.error.message})

    def _handle_server_request(self, payload: JSONRPCRequest) -> None:
        """
        处理带method的输出
        * commandExecution/requestApproval
        * tool/requestInput
        * item/tool/requestUserInput
        """
        method = str(payload.method)
        request_id = payload.id.root
        params = self._model_dump(payload.params)

        if method == "item/commandExecution/requestApproval":
            self._respond_to_server_request(request_id, CommandExecutionRequestApprovalResponse(decision="accept"))
            return
        if method == "item/fileChange/requestApproval":
            self._respond_to_server_request(request_id, FileChangeRequestApprovalResponse(decision="accept"))
            return
        if method == "item/permissions/requestApproval":
            granted_permissions = {}
            if isinstance(params, dict):
                granted_permissions = dict(params.get("permissions") or {})
            self._respond_to_server_request(
                request_id,
                PermissionsRequestApprovalResponse(
                    permissions=GrantedPermissionProfile(**granted_permissions),
                    scope="turn",
                    strictAutoReview=False,
                ),
            )
            return
        if method == "item/tool/requestUserInput":
            questions = params.get("questions", []) if isinstance(params, dict) else []
            answers: dict[str, Any] = {}
            for question in questions:
                question_id = str(question.get("id", "") or "") if isinstance(question, dict) else ""
                if question_id:
                    answers[question_id] = {"answers": [""]}
            self._respond_to_server_request(request_id, ToolRequestUserInputResponse(answers=answers))
            return
        if method == "mcpServer/elicitation/request":
            self._respond_to_server_request(request_id, McpServerElicitationRequestResponse(action="decline", content=None))
            return

        self._respond_to_server_request(request_id, {})
        if self._active_turn_id:
            self._record_event(
                self._active_turn_id,
                "log",
                content=f"unhandled Codex server request: {method}",
                payload=self._model_dump(params) if params is not None else {},
            )

    def _respond_to_server_request(self, request_id: Any, result: Any) -> None:
        """Return a JSON-RPC success response for a server-initiated request."""
        self._write_rpc({"jsonrpc": "2.0", "id": request_id, "result": self._model_dump(result)})

    def _handle_notification(self, payload: JSONRPCNotification) -> None:
        """
        处理notification输出
        * turn/started
        * turn/updated turn/stream
        * turn/completed
        * turn/failed
        """
        method = str(payload.method)
        params = self._model_dump(payload.params)

        if method == "turn/started":
            turn = params.get("turn", {}) if isinstance(params, dict) else {}
            remote_turn_id = str((turn or {}).get("id", "") or "")
            if remote_turn_id:
                self._active_remote_turn_id = remote_turn_id
            self._record_event(self._active_turn_id, "status", content="running")
            return
        if method in {"turn/updated", "turn/stream", "turn/diff/updated", "turn/plan/updated"}:
            self._handle_turn_update(params if isinstance(params, dict) else {})
            return
        if method == "turn/completed":
            self._handle_turn_completed(params if isinstance(params, dict) else {})
            return
        if method == "turn/failed":
            self._handle_turn_failed(params if isinstance(params, dict) else {})
            return
        if not method.startswith("item/"):
            if self._active_turn_id:
                self._record_event(
                    self._active_turn_id,
                    "log",
                    content=f"unhandled Codex notification: {method}",
                    payload=params if isinstance(params, dict) else {},
                )
            return
        if method in {"item/started", "item/updated", "item/completed"}:
            self._handle_item_notification(method, params if isinstance(params, dict) else {})
            return
        if method in {
            "item/agentMessage/delta",
            "item/reasoning/textDelta",
            "item/commandExecution/outputDelta",
            "item/fileChange/outputDelta",
            "item/commandExecution/terminalInteraction",
        }:
            self._handle_item_delta_notification(method, params if isinstance(params, dict) else {})
            return
        if self._active_turn_id:
            self._record_event(
                self._active_turn_id,
                "log",
                content=f"unhandled Codex item notification: {method}",
                payload=params if isinstance(params, dict) else {},
            )

    def _handle_turn_update(self, params: dict[str, Any]) -> None:
        """Merge any usage updates emitted before turn completion."""
        turn = params.get("turn", {}) or {}
        usage = turn.get("usage", {}) or {}
        if not usage:
            return
        self._replace_usage(
            self._active_turn_id,
            TokenUsageSnapshot(
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                cache_read_tokens=int(usage.get("cache_read_tokens", 0) or 0),
                cache_write_tokens=int(usage.get("cache_write_tokens", 0) or 0),
                context_window_tokens=self.config.context_window_tokens,
            ),
        )

    def _handle_turn_completed(self, params: dict[str, Any]) -> None:
        """Finalize the active turn from a completion notification."""
        turn = params.get("turn", {}) or {}
        usage = turn.get("usage", {}) or {}
        status = str(turn.get("status", "completed") or "completed")
        current_turn_id = self._active_turn_id
        current_snapshot = self._last_turn if not current_turn_id else None
        if not current_turn_id and current_snapshot is not None and current_snapshot.status == "timeout":
            self._active_remote_turn_id = ""
            self._item_text_buffers.clear()
            return
        final_status = "completed"
        final_error = ""
        if status == "failed":
            final_status = "failed"
            final_error = self._extract_error_message(turn.get("error")) or "codex turn failed"
        elif status in {"cancelled", "canceled", "aborted", "interrupted"}:
            final_status = "aborted"
            final_error = "codex turn aborted"
        self._complete_turn(
            self._active_turn_id,
            status=final_status,
            error=final_error,
            session_id=self._thread_id,
            usage=TokenUsageSnapshot(
                input_tokens=int(usage.get("input_tokens", 0) or 0),
                output_tokens=int(usage.get("output_tokens", 0) or 0),
                cache_read_tokens=int(usage.get("cache_read_tokens", 0) or 0),
                cache_write_tokens=int(usage.get("cache_write_tokens", 0) or 0),
                context_window_tokens=self.config.context_window_tokens,
            ),
        )
        self._active_turn_id = ""
        self._active_remote_turn_id = ""
        self._item_text_buffers.clear()

    def _handle_turn_failed(self, params: dict[str, Any]) -> None:
        """Finalize the active turn from an explicit failure notification."""
        turn = params.get("turn", {}) or {}
        self._complete_turn(
            self._active_turn_id,
            status="failed",
            error=self._extract_error_message(turn.get("error")) or "codex turn failed",
            session_id=self._thread_id,
        )
        self._active_turn_id = ""
        self._active_remote_turn_id = ""
        self._item_text_buffers.clear()

    def _handle_item_notification(self, method: str, params: dict[str, Any]) -> None:
        """Convert item lifecycle events into managed runtime events."""
        item = params.get("item", {}) or {}
        item_type = str(item.get("type", "") or "")
        item_id = str(item.get("id", "") or "")

        if item_type == "commandExecution":
            self._handle_command_execution_item(method, item_id, item)
            return
        if item_type == "fileChange":
            self._handle_file_change_item(method, item_id, item)
            return
        if item_type == "agentMessage":
            self._handle_agent_message_item(method, item_id, item)
            return
        if item_type == "reasoning":
            self._handle_reasoning_item(method, item_id, item)
            return
        if method == "item/completed":
            self._record_event(
                self._active_turn_id,
                "log",
                content=f"completed item type={item_type}",
                call_id=item_id,
                payload=dict(item),
            )

    def _handle_item_delta_notification(self, method: str, params: dict[str, Any]) -> None:
        """Convert standard Codex delta notifications into runtime events."""
        item_id = str(params.get("itemId", "") or "")
        delta = str(params.get("delta", "") or "")
        if not delta:
            return
        if method == "item/agentMessage/delta":
            self._item_text_buffers[item_id] = self._item_text_buffers.get(item_id, "") + delta
            self._record_event(self._active_turn_id, "text", call_id=item_id, content=delta)
            self._set_final_output(self._active_turn_id, self._item_text_buffers[item_id])
        elif method == "item/reasoning/textDelta":
            self._record_event(self._active_turn_id, "thinking", call_id=item_id, content=delta)
        elif method == "item/commandExecution/outputDelta":
            self._record_event(self._active_turn_id, "log", call_id=item_id, content=delta, payload={"item_type": "commandExecution"})
        elif method == "item/fileChange/outputDelta":
            self._record_event(self._active_turn_id, "log", call_id=item_id, content=delta, payload={"item_type": "fileChange"})
        elif method == "item/commandExecution/terminalInteraction":
            self._record_event(
                self._active_turn_id,
                "log",
                call_id=item_id,
                content=delta,
                payload={"item_type": "commandExecution", "stream": "terminalInteraction"},
            )

    def _handle_command_execution_item(self, method: str, item_id: str, item: dict[str, Any]) -> None:
        """Map command execution items to tool_use/tool_result events."""
        if method == "item/started":
            self._record_event(
                self._active_turn_id,
                "tool_use",
                call_id=item_id,
                tool_name="exec_command",
                payload={
                    "command": item.get("command", ""),
                    "status": item.get("status", ""),
                },
            )
        elif method == "item/updated":
            stream = str(item.get("stream", "") or "")
            delta = str(item.get("delta", "") or item.get("text", "") or "")
            if delta:
                self._record_event(
                    self._active_turn_id,
                    "log",
                    call_id=item_id,
                    content=delta,
                    payload={"stream": stream, "item_type": "commandExecution"},
                )
        elif method == "item/completed":
            content = item.get("aggregatedOutput", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=True)
            self._record_event(
                self._active_turn_id,
                "tool_result",
                call_id=item_id,
                tool_name="exec_command",
                content=content,
            )

    def _handle_file_change_item(self, method: str, item_id: str, item: dict[str, Any]) -> None:
        """Map file change items to patch-related tool events."""
        if method == "item/started":
            self._record_event(
                self._active_turn_id,
                "tool_use",
                call_id=item_id,
                tool_name="patch_apply",
                payload={"status": item.get("status", "")},
            )
        elif method == "item/updated":
            self._record_event(
                self._active_turn_id,
                "log",
                call_id=item_id,
                content=str(item.get("message", "") or ""),
                payload={"item_type": "fileChange"},
            )
        elif method == "item/completed":
            self._record_event(
                self._active_turn_id,
                "tool_result",
                call_id=item_id,
                tool_name="patch_apply",
                content=str(item.get("summary", "") or ""),
            )

    def _handle_agent_message_item(self, method: str, item_id: str, item: dict[str, Any]) -> None:
        """Map agent message items to streaming text and final output state."""
        if method == "item/started":
            self._item_text_buffers[item_id] = ""
            return
        if method == "item/updated":
            delta = self._extract_agent_message_delta(item)
            if delta:
                self._item_text_buffers[item_id] = self._item_text_buffers.get(item_id, "") + delta
                self._record_event(self._active_turn_id, "text", call_id=item_id, content=delta)
                self._set_final_output(self._active_turn_id, self._item_text_buffers[item_id])
            return
        if method == "item/completed":
            text = self._extract_agent_message_text(item)
            if text:
                buffered = self._item_text_buffers.get(item_id, "")
                if text != buffered:
                    suffix = text[len(buffered):] if text.startswith(buffered) else text
                    if suffix:
                        self._record_event(self._active_turn_id, "text", call_id=item_id, content=suffix)
                self._set_final_output(self._active_turn_id, text)
            self._item_text_buffers.pop(item_id, None)

    def _handle_reasoning_item(self, method: str, item_id: str, item: dict[str, Any]) -> None:
        """Map reasoning items to internal thinking events."""
        if method == "item/updated":
            delta = str(item.get("delta", "") or item.get("text", "") or "")
            if delta:
                self._record_event(self._active_turn_id, "thinking", call_id=item_id, content=delta)
        elif method == "item/completed":
            text = str(item.get("text", "") or "")
            if text:
                self._record_event(self._active_turn_id, "thinking", call_id=item_id, content=text)

    def _extract_agent_message_delta(self, item: dict[str, Any]) -> str:
        """Extract one streaming text delta from an agent message item."""
        delta = item.get("delta")
        if isinstance(delta, str):
            return delta
        text = item.get("text")
        if isinstance(text, str):
            return text
        content = item.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    piece = block.get("text")
                    if isinstance(piece, str):
                        parts.append(piece)
            return "".join(parts)
        return ""

    def _extract_agent_message_text(self, item: dict[str, Any]) -> str:
        """Extract the full text body from a completed agent message item."""
        text = item.get("text")
        if isinstance(text, str):
            return text
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    piece = block.get("text")
                    if isinstance(piece, str):
                        parts.append(piece)
            return "".join(parts)
        return ""

    def _extract_thread_id(self, response: dict[str, Any]) -> str:
        """Extract a thread identifier from a thread/start or thread/resume response."""
        return str((((response or {}).get("thread")) or {}).get("id", "") or "")

    def _extract_turn_id(self, response: dict[str, Any]) -> str:
        """Extract a remote turn identifier from a turn/start response."""
        return str((((response or {}).get("turn")) or {}).get("id", "") or "")

    def _extract_error_message(self, error: Any) -> str:
        """Extract a stable error string from a protocol error payload."""
        if isinstance(error, dict):
            return str(error.get("message", "") or json.dumps(error, ensure_ascii=True))
        if error is None:
            return ""
        return str(error)

    def _cancel_active_turn(self, reason: str, status: str) -> None:
        """Interrupt the active Codex turn when possible and finalize local state."""
        active_turn_id = self._active_turn_id
        remote_turn_id = self._active_remote_turn_id
        if not active_turn_id and self._last_turn is not None and self._last_turn.status == "timeout":
            self._active_remote_turn_id = ""
            self._item_text_buffers.clear()
            return
        if remote_turn_id and self._thread_id and self._process is not None and self._process.poll() is None:
            try:
                self._rpc_request(
                    "turn/interrupt",
                    TurnInterruptParams(threadId=self._thread_id, turnId=remote_turn_id),
                    timeout=min(5.0, self.config.startup_timeout_seconds),
                )
            except Exception:
                pass
        if active_turn_id:
            self._complete_turn(active_turn_id, status=status, error=reason, session_id=self._thread_id)
            self._active_turn_id = ""
            self._active_remote_turn_id = ""
            self._item_text_buffers.clear()

    def _shutdown_impl(self) -> None:
        """Shut down Codex process resources and join helper threads."""
        self._cancel_active_turn("agent runtime shutdown", "aborted")
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3.0)
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
        self._process = None

    def _config_override_args(self) -> list[str]:
        """Build ``codex -c`` overrides from reused model-provider config."""
        args: list[str] = []
        reused_skills = self.config.runtime_options.get("reused_skills")
        if isinstance(reused_skills, list) and reused_skills:
            args.extend(["-c", f"skills.config={json.dumps(reused_skills, ensure_ascii=True)}"])

        reused_mcp = self.config.runtime_options.get("reused_mcp")
        if isinstance(reused_mcp, dict) and reused_mcp:
            args.extend(["-c", f"mcp_servers={json.dumps(reused_mcp, ensure_ascii=True)}"])

        reused_reasoning_effort = self.config.runtime_options.get("reused_model_reasoning_effort")
        if reused_reasoning_effort:
            args.extend(["-c", f"model_reasoning_effort={json.dumps(str(reused_reasoning_effort), ensure_ascii=True)}"])
        return args

    def _prepare_codex_home(self) -> Path:
        """Prepare an isolated CODEX_HOME with minimal reused config and auth state."""
        codex_home = self.workspace.root / ".codex"
        codex_home.mkdir(parents=True, exist_ok=True)

        provider_root = self.workspace.root
        self._copy_if_missing(provider_root / ".codex" / "config.toml", codex_home / "config.toml")
        self._copy_if_missing(provider_root / ".codex" / "auth.json", codex_home / "auth.json")

        self._write_minimal_codex_config(codex_home / "config.toml")
        self._write_reused_auth(codex_home / "auth.json")
        return codex_home

    def _copy_if_missing(self, source: Path, target: Path) -> None:
        """Copy a config artifact into CODEX_HOME when a local copy does not yet exist."""
        if not source.exists() or target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def _write_minimal_codex_config(self, path: Path) -> None:
        """Write a minimal config.toml for base_url/model reuse when no snapshot exists yet."""
        if path.exists():
            return
        payload: dict[str, Any] = {}
        if self.config.model:
            payload["model"] = self.config.model
        reused_base_url = self.config.runtime_options.get("reused_base_url")
        if reused_base_url:
            payload["base_url"] = str(reused_base_url)
        reused_reasoning_effort = self.config.runtime_options.get("reused_model_reasoning_effort")
        if reused_reasoning_effort:
            payload["model_reasoning_effort"] = str(reused_reasoning_effort)
        if not payload:
            return
        rendered = []
        for key, value in payload.items():
            rendered.append(f"{key} = {json.dumps(value, ensure_ascii=True)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(rendered) + "\n", encoding="utf-8")

    def _write_reused_auth(self, path: Path) -> None:
        """Write a minimal auth.json into CODEX_HOME when reuse exposed auth tokens."""
        if path.exists():
            return
        reused_auth = self.config.runtime_options.get("reused_auth")
        if not isinstance(reused_auth, dict) or not reused_auth:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reused_auth, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
