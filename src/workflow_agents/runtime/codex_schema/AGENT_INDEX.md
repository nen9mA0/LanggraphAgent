# Codex Schema Agent Index

This directory contains generated Pydantic models from the codex app-server schema.
Use this index to avoid opening large union files until you know the exact target type.

## Progressive Disclosure

1. Read AGENT_INDEX.md first.
1. Use `agent_index.json.client_requests`, `server_requests`, or `server_notifications` to map a method to the exact payload model.
1. Open only the target file and line for the params model or dedicated schema file.
1. If the type is duplicated, prefer the dedicated standalone file instead of `ClientRequest.py`.
1. Open `ClientRequest.py` only for inline-only request params or the request union itself.
1. Open `json_schema/codex_app_server_protocol*.json` only when the index points there for server requests, notifications, or response models with no generated Python file.

## Fast Paths

- Raw JSON-RPC envelope: `JSONRPCMessage.py`, `JSONRPCRequest.py`, `JSONRPCResponse.py`, `JSONRPCError.py`, `JSONRPCNotification.py`.
- Client-to-server request dispatch: `agent_index.json -> client_requests`.
- Client request response lookup: `agent_index.json -> client_request_responses`.
- Server-to-client request dispatch: `agent_index.json -> server_requests`.
- Server-to-client notification dispatch: `agent_index.json -> server_notifications`.
- Client-sent notification dispatch: `agent_index.json -> client_notifications`.
- Exact class fields: `agent_index.json -> class_index[ClassName]`.
- Approval payloads: files under the `approvals` bucket.
- Raw aggregate protocol sources: `json_schema/codex_app_server_protocol.schemas.json`, `json_schema/codex_app_server_protocol.v2.schemas.json`.
- Search/tool payloads: `FuzzyFileSearch*.py`, `DynamicToolCall*.py`, `McpServerElicitation*.py`.

## Protocol Coverage

| Surface | Count | Primary source |
| --- | ---: | --- |
| Client requests | 81 | `ClientRequest.py` + index metadata |
| Client request responses | 81 | raw protocol schemas, with generated file preference when available |
| Server requests | 10 | raw protocol schema unions |
| Server notifications | 64 | raw protocol schema unions |
| Client notifications | 1 | `ClientNotification.py` |

## Client Request Families

| Family | Request count |
| --- | ---: |
| `account` | 6 |
| `app` | 1 |
| `command` | 4 |
| `config` | 4 |
| `configRequirements` | 1 |
| `experimentalFeature` | 2 |
| `externalAgentConfig` | 2 |
| `feedback` | 1 |
| `fs` | 9 |
| `fuzzyFileSearch` | 1 |
| `hooks` | 1 |
| `initialize` | 1 |
| `marketplace` | 3 |
| `mcpServer` | 3 |
| `mcpServerStatus` | 1 |
| `model` | 1 |
| `modelProvider` | 1 |
| `permissionProfile` | 1 |
| `plugin` | 11 |
| `review` | 1 |
| `skills` | 2 |
| `thread` | 19 |
| `turn` | 3 |
| `windowsSandbox` | 2 |

## Server Request Families

| Family | Request count |
| --- | ---: |
| `account` | 1 |
| `applyPatchApproval` | 1 |
| `attestation` | 1 |
| `execCommandApproval` | 1 |
| `item` | 5 |
| `mcpServer` | 1 |

## Server Notification Families

| Family | Notification count |
| --- | ---: |
| `account` | 3 |
| `app` | 1 |
| `command` | 1 |
| `configWarning` | 1 |
| `deprecationNotice` | 1 |
| `error` | 1 |
| `externalAgentConfig` | 1 |
| `fs` | 1 |
| `fuzzyFileSearch` | 2 |
| `guardianWarning` | 1 |
| `hook` | 2 |
| `item` | 14 |
| `mcpServer` | 2 |
| `model` | 2 |
| `process` | 2 |
| `remoteControl` | 1 |
| `serverRequest` | 1 |
| `skills` | 1 |
| `thread` | 19 |
| `turn` | 4 |
| `warning` | 1 |
| `windows` | 1 |
| `windowsSandbox` | 1 |

## File Buckets

- `approvals`: `ApplyPatchApprovalParams.py`, `ApplyPatchApprovalResponse.py`, `CommandExecutionRequestApprovalParams.py`, `CommandExecutionRequestApprovalResponse.py`, `ExecCommandApprovalParams.py`, `ExecCommandApprovalResponse.py`, `FileChangeRequestApprovalParams.py`, `FileChangeRequestApprovalResponse.py`
- `auth_and_attestation`: `AttestationGenerateParams.py`, `AttestationGenerateResponse.py`, `ChatgptAuthTokensRefreshParams.py`, `ChatgptAuthTokensRefreshResponse.py`
- `dynamic_tools`: `DynamicToolCallParams.py`, `DynamicToolCallResponse.py`
- `entrypoints`: `ClientNotification.py`, `ClientRequest.py`, `JSONRPCMessage.py`
- `fuzzy_search`: `FuzzyFileSearchParams.py`, `FuzzyFileSearchResponse.py`, `FuzzyFileSearchSessionCompletedNotification.py`, `FuzzyFileSearchSessionUpdatedNotification.py`
- `jsonrpc`: `JSONRPCError.py`, `JSONRPCErrorError.py`, `JSONRPCNotification.py`, `JSONRPCRequest.py`, `JSONRPCResponse.py`
- `mcp_elicitation`: `McpServerElicitationRequestParams.py`, `McpServerElicitationRequestResponse.py`
- `misc`: `components.py`
- `raw_protocol_schemas`: `json_schema/codex_app_server_protocol.schemas.json`, `json_schema/codex_app_server_protocol.v2.schemas.json`

## Protocol Notes

- Server-initiated requests and most server notifications are indexed from the raw aggregate protocol schemas because they are not emitted as standalone generated Python files in this directory.
- When adapting turn-time approvals, prefer the canonical item-scoped request methods from `server_requests` such as `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, and `item/tool/requestUserInput`.
- Streaming notifications in the raw protocol are fine-grained (`item/agentMessage/delta`, `item/reasoning/textDelta`, `item/commandExecution/outputDelta`, `item/fileChange/outputDelta`, `turn/diff/updated`, `turn/plan/updated`). Avoid assuming only coarse aliases exist.
- Legacy-style approval requests such as `applyPatchApproval` and `execCommandApproval` remain indexed because they are still present in the upstream schema.

## Preferred Duplicates

These class names exist in multiple files. Use the preferred location first to minimize context.

| Class | Preferred location | Other locations |
| --- | --- | --- |
| `AbsolutePathBuf` | `CommandExecutionRequestApprovalParams.py:12` | `ClientRequest.py:337` |
| `AcceptWithExecpolicyAmendment` | `CommandExecutionRequestApprovalParams.py:78` | `CommandExecutionRequestApprovalResponse.py:20` |
| `ApplyNetworkPolicyAmendment` | `CommandExecutionRequestApprovalParams.py:286` | `CommandExecutionRequestApprovalResponse.py:49` |
| `ApprovedExecpolicyAmendment` | `ApplyPatchApprovalResponse.py:21` | `ExecCommandApprovalResponse.py:21` |
| `CommandExecutionApprovalDecision` | `CommandExecutionRequestApprovalParams.py:297` | `CommandExecutionRequestApprovalResponse.py:60` |
| `CommandExecutionApprovalDecision1` | `CommandExecutionRequestApprovalParams.py:70` | `CommandExecutionRequestApprovalResponse.py:12` |
| `CommandExecutionApprovalDecision2` | `CommandExecutionRequestApprovalParams.py:74` | `CommandExecutionRequestApprovalResponse.py:16` |
| `CommandExecutionApprovalDecision3` | `CommandExecutionRequestApprovalParams.py:82` | `CommandExecutionRequestApprovalResponse.py:24` |
| `CommandExecutionApprovalDecision4` | `CommandExecutionRequestApprovalParams.py:290` | `CommandExecutionRequestApprovalResponse.py:53` |
| `CommandExecutionApprovalDecision5` | `CommandExecutionRequestApprovalParams.py:89` | `CommandExecutionRequestApprovalResponse.py:31` |
| `CommandExecutionApprovalDecision6` | `CommandExecutionRequestApprovalParams.py:93` | `CommandExecutionRequestApprovalResponse.py:35` |
| `FuzzyFileSearchMatchType` | `FuzzyFileSearchResponse.py:12` | `FuzzyFileSearchSessionUpdatedNotification.py:12` |

Full duplicate list: `agent_index.json -> duplicates` (41 entries).

## High-Value Entry Files

| File | Top-level class | Notes |
| --- | --- | --- |
| `ApplyPatchApprovalParams.py` | `ApplyPatchApprovalParams` | standalone schema |
| `ClientNotification.py` | `ClientNotification` | standalone schema |
| `ClientRequest.py` | `ClientRequest` | standalone schema |
| `CommandExecutionRequestApprovalParams.py` | `CommandExecutionRequestApprovalParams` | standalone schema |
| `CommandExecutionRequestApprovalResponse.py` | `CommandExecutionRequestApprovalResponse` | standalone schema |
| `DynamicToolCallParams.py` | `DynamicToolCallParams` | standalone schema |
| `DynamicToolCallResponse.py` | `DynamicToolCallResponse` | standalone schema |
| `ExecCommandApprovalParams.py` | `ExecCommandApprovalParams` | standalone schema |
| `FuzzyFileSearchParams.py` | `FuzzyFileSearchParams` | used by fuzzyFileSearch; duplicated name; prefer standalone file |
| `FuzzyFileSearchResponse.py` | `FuzzyFileSearchResponse` | standalone schema |
| `JSONRPCMessage.py` | `JSONRPCMessage` | standalone schema |

## Raw Protocol Sources

| File | Purpose |
| --- | --- |
| `json_schema/codex_app_server_protocol.schemas.json` | Aggregate protocol schema containing the client request union, server request union, and notification union. |
| `json_schema/codex_app_server_protocol.v2.schemas.json` | Flattened v2 definitions used for notification payload and response-model lookups. |

## Regeneration

```bash
python src/workflow_agents/runtime/codex_schema/build_agent_index.py
```

Machine-readable source of truth: `agent_index.json`.
