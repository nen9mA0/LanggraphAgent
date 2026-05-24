# Codex Schema Agent Index

This directory contains generated Pydantic models from the codex app-server schema.
Use this index to avoid opening large union files until you know the exact target type.

## Progressive Disclosure

1. Read AGENT_INDEX.md first.
1. Use agent_index.json.client_requests to map a method to the exact params model.
1. Open only the target file and line for the params model or dedicated schema file.
1. If the type is duplicated, prefer the dedicated standalone file instead of `ClientRequest.py`.
1. Open `ClientRequest.py` only for inline-only request params or the request union itself.

## Fast Paths

- Raw JSON-RPC envelope: `JSONRPCMessage.py`, `JSONRPCRequest.py`, `JSONRPCResponse.py`, `JSONRPCError.py`, `JSONRPCNotification.py`.
- App-level request dispatch: `agent_index.json -> client_requests`.
- App-level notification dispatch: `agent_index.json -> client_notifications`.
- Exact class fields: `agent_index.json -> class_index[ClassName]`.
- Approval payloads: files under the `approvals` bucket.
- Search/tool payloads: `FuzzyFileSearch*.py`, `DynamicToolCall*.py`, `McpServerElicitation*.py`.

## Request Families

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

## File Buckets

- `approvals`: `ApplyPatchApprovalParams.py`, `ApplyPatchApprovalResponse.py`, `CommandExecutionRequestApprovalParams.py`, `CommandExecutionRequestApprovalResponse.py`, `ExecCommandApprovalParams.py`, `ExecCommandApprovalResponse.py`, `FileChangeRequestApprovalParams.py`, `FileChangeRequestApprovalResponse.py`
- `auth_and_attestation`: `AttestationGenerateParams.py`, `AttestationGenerateResponse.py`, `ChatgptAuthTokensRefreshParams.py`, `ChatgptAuthTokensRefreshResponse.py`
- `dynamic_tools`: `DynamicToolCallParams.py`, `DynamicToolCallResponse.py`
- `entrypoints`: `ClientNotification.py`, `ClientRequest.py`, `JSONRPCMessage.py`
- `fuzzy_search`: `FuzzyFileSearchParams.py`, `FuzzyFileSearchResponse.py`, `FuzzyFileSearchSessionCompletedNotification.py`, `FuzzyFileSearchSessionUpdatedNotification.py`
- `jsonrpc`: `JSONRPCError.py`, `JSONRPCErrorError.py`, `JSONRPCNotification.py`, `JSONRPCRequest.py`, `JSONRPCResponse.py`
- `mcp_elicitation`: `McpServerElicitationRequestParams.py`, `McpServerElicitationRequestResponse.py`
- `misc`: `codex_app_server_protocol.schemas.py`, `codex_app_server_protocol.v2.schemas.py`, `components.py`

## Preferred Duplicates

These class names exist in multiple files. Use the preferred location first to minimize context.

| Class | Preferred location | Other locations |
| --- | --- | --- |
| `AbsolutePathBuf` | `CommandExecutionRequestApprovalParams.py:12` | `ClientRequest.py:337`, `codex_app_server_protocol.schemas.py:1063`, `codex_app_server_protocol.v2.schemas.py:17` |
| `AcceptWithExecpolicyAmendment` | `CommandExecutionRequestApprovalParams.py:78` | `CommandExecutionRequestApprovalResponse.py:20`, `codex_app_server_protocol.schemas.py:443` |
| `AccountLoginCompletedNotification` | `codex_app_server_protocol.schemas.py:1152` | `codex_app_server_protocol.v2.schemas.py:482` |
| `AccountRateLimitsUpdatedNotification` | `codex_app_server_protocol.schemas.py:4762` | `codex_app_server_protocol.v2.schemas.py:6223` |
| `AccountUpdatedNotification` | `codex_app_server_protocol.schemas.py:3881` | `codex_app_server_protocol.v2.schemas.py:5518` |
| `ActivePermissionProfile` | `codex_app_server_protocol.schemas.py:2478` | `codex_app_server_protocol.v2.schemas.py:1679` |
| `ActiveTurnNotSteerable` | `codex_app_server_protocol.schemas.py:4345` | `codex_app_server_protocol.v2.schemas.py:5250` |
| `AddCreditsNudgeCreditType` | `codex_app_server_protocol.schemas.py:1898` | `ClientRequest.py:344`, `codex_app_server_protocol.v2.schemas.py:1445` |
| `AdditionalFileSystemPermissions` | `CommandExecutionRequestApprovalParams.py:268` | `codex_app_server_protocol.schemas.py:5098`, `codex_app_server_protocol.v2.schemas.py:6269` |
| `AdditionalNetworkPermissions` | `CommandExecutionRequestApprovalParams.py:19` | `codex_app_server_protocol.schemas.py:1158`, `codex_app_server_protocol.v2.schemas.py:3566` |
| `AdditionalPermissionProfile` | `CommandExecutionRequestApprovalParams.py:279` | `codex_app_server_protocol.schemas.py:5491` |
| `AgentMessageDeltaNotification` | `codex_app_server_protocol.schemas.py:1162` | `codex_app_server_protocol.v2.schemas.py:3746` |

Full duplicate list: `agent_index.json -> duplicates` (884 entries).

## High-Value Entry Files

| File | Top-level class | Notes |
| --- | --- | --- |
| `ApplyPatchApprovalParams.py` | `ApplyPatchApprovalParams` | duplicated name; prefer standalone file |
| `ClientNotification.py` | `ClientNotification` | duplicated name; prefer standalone file |
| `ClientRequest.py` | `ClientRequest` | duplicated name; prefer standalone file |
| `CommandExecutionRequestApprovalParams.py` | `CommandExecutionRequestApprovalParams` | duplicated name; prefer standalone file |
| `CommandExecutionRequestApprovalResponse.py` | `CommandExecutionRequestApprovalResponse` | duplicated name; prefer standalone file |
| `DynamicToolCallParams.py` | `DynamicToolCallParams` | duplicated name; prefer standalone file |
| `DynamicToolCallResponse.py` | `DynamicToolCallResponse` | duplicated name; prefer standalone file |
| `ExecCommandApprovalParams.py` | `ExecCommandApprovalParams` | duplicated name; prefer standalone file |
| `FuzzyFileSearchParams.py` | `FuzzyFileSearchParams` | used by fuzzyFileSearch; duplicated name; prefer standalone file |
| `FuzzyFileSearchResponse.py` | `FuzzyFileSearchResponse` | duplicated name; prefer standalone file |
| `JSONRPCMessage.py` | `JSONRPCMessage` | duplicated name; prefer standalone file |

## Regeneration

```bash
python src/workflow_agents/runtime/codex_schema/build_agent_index.py
```

Machine-readable source of truth: `agent_index.json`.
