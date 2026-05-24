from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCHEMA_DIR.parents[3]
OUTPUT_MARKDOWN = SCHEMA_DIR / "AGENT_INDEX.md"
OUTPUT_JSON = SCHEMA_DIR / "agent_index.json"
SKIP_FILES = {
    OUTPUT_MARKDOWN.name,
    OUTPUT_JSON.name,
    Path(__file__).name,
    "codex_app_server_protocol.schemas.py",
    "codex_app_server_protocol.v2.schemas.py",
}
RAW_PROTOCOL_SCHEMA = SCHEMA_DIR / "json_schema" / "codex_app_server_protocol.schemas.json"
RAW_PROTOCOL_V2_SCHEMA = SCHEMA_DIR / "json_schema" / "codex_app_server_protocol.v2.schemas.json"

CLIENT_RESPONSE_OVERRIDES = {
    "account/logout": "LogoutAccountResponse",
    "account/rateLimits/read": "GetAccountRateLimitsResponse",
    "config/batchWrite": "ConfigWriteResponse",
    "config/mcpServer/reload": "McpServerRefreshResponse",
    "config/value/write": "ConfigWriteResponse",
}

PROTOCOL_NOTES = [
    "Server-initiated requests and most server notifications are indexed from the raw aggregate protocol schemas because they are not emitted as standalone generated Python files in this directory.",
    "When adapting turn-time approvals, prefer the canonical item-scoped request methods from `server_requests` such as `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, and `item/tool/requestUserInput`.",
    "Streaming notifications in the raw protocol are fine-grained (`item/agentMessage/delta`, `item/reasoning/textDelta`, `item/commandExecution/outputDelta`, `item/fileChange/outputDelta`, `turn/diff/updated`, `turn/plan/updated`). Avoid assuming only coarse aliases exist.",
    "Legacy-style approval requests such as `applyPatchApproval` and `execCommandApproval` remain indexed because they are still present in the upstream schema.",
]


@dataclass
class FieldInfo:
    name: str
    annotation: str
    line: int


@dataclass
class ClassInfo:
    name: str
    kind: str
    line: int
    bases: list[str]
    fields: list[FieldInfo]
    enum_values: list[str]


@dataclass
class RawSchemaSource:
    path: Path
    repo_path: str
    definitions: dict[str, Any]
    lines_by_definition: dict[str, int]


def relpath(path: Path) -> str:
    return path.relative_to(SCHEMA_DIR).as_posix()


def repo_relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def class_kind(bases: list[str]) -> str:
    if any(base == "Enum" or base.endswith(".Enum") for base in bases):
        return "enum"
    if any(base.startswith("RootModel") for base in bases):
        return "root_model"
    if any(base == "BaseModel" or base.endswith(".BaseModel") for base in bases):
        return "model"
    return "class"


def parse_python_file(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    classes: list[ClassInfo] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        bases = [unparse(base) for base in node.bases]
        fields: list[FieldInfo] = []
        enum_values: list[str] = []

        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(
                    FieldInfo(
                        name=item.target.id,
                        annotation=unparse(item.annotation),
                        line=item.lineno,
                    )
                )
            elif isinstance(item, ast.Assign) and len(item.targets) == 1:
                target = item.targets[0]
                if isinstance(target, ast.Name) and isinstance(item.value, ast.Constant):
                    enum_values.append(repr(item.value.value))

        classes.append(
            ClassInfo(
                name=node.name,
                kind=class_kind(bases),
                line=node.lineno,
                bases=bases,
                fields=fields,
                enum_values=enum_values,
            )
        )

    top_level = next((cls.name for cls in classes if cls.name == path.stem), None)
    return {
        "file": relpath(path),
        "repo_path": repo_relpath(path),
        "path": path,
        "top_level_class": top_level,
        "classes": classes,
    }


def class_lookup(files_data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file_data in files_data:
        for cls in file_data["classes"]:
            lookup[cls.name].append(
                {
                    "file": file_data["file"],
                    "repo_path": file_data["repo_path"],
                    "line": cls.line,
                    "kind": cls.kind,
                }
            )
    return dict(lookup)


def preferred_location(name: str | None, lookup: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    if not name:
        return None
    locations = lookup.get(name, [])
    if not locations:
        return None

    non_client_request = [loc for loc in locations if loc["file"] != "ClientRequest.py"]
    if non_client_request:
        return sorted(non_client_request, key=lambda item: (item["file"], item["line"]))[0]
    return sorted(locations, key=lambda item: (item["file"], item["line"]))[0]


def load_raw_schema_source(path: Path, *, nested_v2: bool) -> RawSchemaSource:
    raw_text = path.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    definitions = data["definitions"]["v2"] if nested_v2 else data["definitions"]

    names = set(definitions.keys())
    lines_by_definition: dict[str, int] = {}
    pattern = re.compile(r'"([^"]+)":\s*\{')
    for lineno, line in enumerate(raw_text.splitlines(), start=1):
        match = pattern.search(line)
        if not match:
            continue
        name = match.group(1)
        if name in names and name not in lines_by_definition:
            lines_by_definition[name] = lineno

    return RawSchemaSource(
        path=path,
        repo_path=repo_relpath(path),
        definitions=definitions,
        lines_by_definition=lines_by_definition,
    )


def schema_definition_location(source: RawSchemaSource, definition_name: str) -> dict[str, Any] | None:
    line = source.lines_by_definition.get(definition_name)
    if line is None:
        return None
    return {
        "file": relpath(source.path),
        "repo_path": source.repo_path,
        "line": line,
        "kind": "schema_definition",
    }


def ref_to_definition_name(schema_ref: str | None) -> str | None:
    if not schema_ref or not schema_ref.startswith("#/definitions/"):
        return None
    return schema_ref.rsplit("/", 1)[-1]


def resolve_schema_ref_location(
    schema_ref: str | None,
    lookup: dict[str, list[dict[str, Any]]],
    raw_main: RawSchemaSource,
    raw_v2: RawSchemaSource,
) -> tuple[str | None, dict[str, Any] | None]:
    definition_name = ref_to_definition_name(schema_ref)
    if definition_name is None:
        return None, None

    if schema_ref.startswith("#/definitions/v2/"):
        return definition_name, schema_definition_location(raw_v2, definition_name)

    location = preferred_location(definition_name, lookup)
    if location is not None:
        return definition_name, location
    return definition_name, schema_definition_location(raw_main, definition_name)


def camelize_title_to_response_name(request_title: str) -> str:
    base = request_title.removesuffix("Request")
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", base) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) + "Response"


def response_name_for_method(
    *,
    method: str,
    params_model: str | None,
    request_title: str | None,
    available_response_names: set[str],
    overrides: dict[str, str] | None = None,
) -> str | None:
    if overrides and method in overrides:
        return overrides[method]

    if params_model and params_model.endswith("Params"):
        candidate = params_model.removesuffix("Params") + "Response"
        if candidate in available_response_names:
            return candidate

    if request_title:
        candidate = camelize_title_to_response_name(request_title)
        if candidate in available_response_names:
            return candidate

    return None


def resolve_model_location(
    model_name: str | None,
    lookup: dict[str, list[dict[str, Any]]],
    raw_main: RawSchemaSource,
    raw_v2: RawSchemaSource,
) -> dict[str, Any] | None:
    if not model_name:
        return None
    location = preferred_location(model_name, lookup)
    if location is not None:
        return location
    return schema_definition_location(raw_main, model_name) or schema_definition_location(raw_v2, model_name)


def protocol_union_entries(union_definition: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in union_definition.get("oneOf", []):
        method = (((entry.get("properties") or {}).get("method") or {}).get("enum") or [None])[0]
        if not method:
            continue
        items.append(
            {
                "method": method,
                "family": method.split("/", 1)[0],
                "title": entry.get("title"),
                "description": entry.get("description"),
                "params_ref": ((entry.get("properties") or {}).get("params") or {}).get("$ref"),
            }
        )
    return items


def build_client_requests(
    files_data: list[dict[str, Any]],
    lookup: dict[str, list[dict[str, Any]]],
    raw_main: RawSchemaSource,
    raw_v2: RawSchemaSource,
) -> list[dict[str, Any]]:
    client_request_file = next(item for item in files_data if item["file"] == "ClientRequest.py")
    raw_request_entries = {
        item["method"]: item for item in protocol_union_entries(raw_main.definitions["ClientRequest"])
    }
    available_response_names = {
        name
        for name in list(raw_main.definitions.keys()) + list(raw_v2.definitions.keys())
        if name.endswith("Response")
    }

    enum_value_by_class: dict[str, str] = {}
    for cls in client_request_file["classes"]:
        if cls.kind == "enum" and len(cls.enum_values) == 1:
            enum_value_by_class[cls.name] = ast.literal_eval(cls.enum_values[0])

    request_entries: list[dict[str, Any]] = []
    for cls in client_request_file["classes"]:
        if not cls.name.startswith("ClientRequest") or cls.name == "ClientRequest":
            continue
        if cls.kind != "model":
            continue

        field_map = {field.name: field for field in cls.fields}
        method_field = field_map.get("method")
        if method_field is None:
            continue

        method = enum_value_by_class.get(method_field.annotation)
        if not method:
            continue

        params_field = field_map.get("params")
        params_model = params_field.annotation if params_field else None
        if params_model == "None":
            params_model = None
        params_location = preferred_location(params_model, lookup) if params_model else None

        raw_entry = raw_request_entries.get(method, {})
        response_model = response_name_for_method(
            method=method,
            params_model=params_model,
            request_title=raw_entry.get("title"),
            available_response_names=available_response_names,
            overrides=CLIENT_RESPONSE_OVERRIDES,
        )

        request_entries.append(
            {
                "method": method,
                "family": method.split("/", 1)[0],
                "request_title": raw_entry.get("title"),
                "request_model": cls.name,
                "request_model_location": {
                    "file": client_request_file["file"],
                    "repo_path": client_request_file["repo_path"],
                    "line": cls.line,
                },
                "params_model": params_model,
                "params_location": params_location,
                "response_model": response_model,
                "response_location": resolve_model_location(response_model, lookup, raw_main, raw_v2),
            }
        )

    return sorted(request_entries, key=lambda item: item["method"])


def build_client_notifications(files_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notification_file = next(item for item in files_data if item["file"] == "ClientNotification.py")
    enum_value_by_class: dict[str, str] = {}
    for cls in notification_file["classes"]:
        if cls.kind == "enum" and len(cls.enum_values) == 1:
            enum_value_by_class[cls.name] = ast.literal_eval(cls.enum_values[0])

    items: list[dict[str, Any]] = []
    for cls in notification_file["classes"]:
        if not cls.name.startswith("ClientNotification") or cls.name == "ClientNotification":
            continue
        field_map = {field.name: field for field in cls.fields}
        method_field = field_map.get("method")
        if method_field is None:
            continue
        method = enum_value_by_class.get(method_field.annotation)
        if not method:
            continue
        items.append(
            {
                "method": method,
                "notification_model": cls.name,
                "location": {
                    "file": notification_file["file"],
                    "repo_path": notification_file["repo_path"],
                    "line": cls.line,
                },
            }
        )

    return sorted(items, key=lambda item: item["method"])


def build_server_requests(
    lookup: dict[str, list[dict[str, Any]]],
    raw_main: RawSchemaSource,
    raw_v2: RawSchemaSource,
) -> list[dict[str, Any]]:
    available_response_names = {
        name
        for name in list(raw_main.definitions.keys()) + list(raw_v2.definitions.keys())
        if name.endswith("Response")
    }

    entries: list[dict[str, Any]] = []
    for item in protocol_union_entries(raw_main.definitions["ServerRequest"]):
        params_model, params_location = resolve_schema_ref_location(item["params_ref"], lookup, raw_main, raw_v2)
        response_model = response_name_for_method(
            method=item["method"],
            params_model=params_model,
            request_title=item["title"],
            available_response_names=available_response_names,
        )
        entries.append(
            {
                "method": item["method"],
                "family": item["family"],
                "request_title": item["title"],
                "description": item["description"],
                "params_model": params_model,
                "params_location": params_location,
                "response_model": response_model,
                "response_location": resolve_model_location(response_model, lookup, raw_main, raw_v2),
            }
        )
    return sorted(entries, key=lambda item: item["method"])


def build_server_notifications(
    lookup: dict[str, list[dict[str, Any]]],
    raw_main: RawSchemaSource,
    raw_v2: RawSchemaSource,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in protocol_union_entries(raw_main.definitions["ServerNotification"]):
        params_model, params_location = resolve_schema_ref_location(item["params_ref"], lookup, raw_main, raw_v2)
        entries.append(
            {
                "method": item["method"],
                "family": item["family"],
                "notification_title": item["title"],
                "description": item["description"],
                "params_model": params_model,
                "params_location": params_location,
            }
        )
    return sorted(entries, key=lambda item: item["method"])


def build_file_summaries(
    files_data: list[dict[str, Any]],
    request_entries: list[dict[str, Any]],
    lookup: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    methods_by_params: dict[str, list[str]] = defaultdict(list)
    for entry in request_entries:
        if entry["params_model"]:
            methods_by_params[entry["params_model"]].append(entry["method"])

    summaries: list[dict[str, Any]] = []
    for file_data in sorted(files_data, key=lambda item: item["file"]):
        top_level_class = file_data["top_level_class"]
        supporting = [
            cls.name
            for cls in file_data["classes"]
            if cls.name != top_level_class and not cls.name.startswith("Method")
        ]
        used_by_methods = methods_by_params.get(top_level_class or "", [])

        summaries.append(
            {
                "file": file_data["file"],
                "repo_path": file_data["repo_path"],
                "top_level_class": top_level_class,
                "top_level_location": (
                    {
                        "file": file_data["file"],
                        "repo_path": file_data["repo_path"],
                        "line": next(cls.line for cls in file_data["classes"] if cls.name == top_level_class),
                    }
                    if top_level_class
                    else None
                ),
                "class_count": len(file_data["classes"]),
                "supporting_classes": supporting[:12],
                "used_by_methods": used_by_methods,
                "has_duplicate_top_level": bool(
                    top_level_class and len(lookup.get(top_level_class, [])) > 1
                ),
            }
        )

    return summaries


def build_duplicates(lookup: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    duplicates: list[dict[str, Any]] = []
    for name, locations in sorted(lookup.items()):
        files = {loc["file"] for loc in locations}
        if len(files) < 2:
            continue
        duplicates.append(
            {
                "name": name,
                "preferred_location": preferred_location(name, lookup),
                "locations": sorted(locations, key=lambda item: (item["file"], item["line"])),
            }
        )
    return duplicates


def build_class_index(files_data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file_data in files_data:
        for cls in file_data["classes"]:
            result[cls.name].append(
                {
                    "file": file_data["file"],
                    "repo_path": file_data["repo_path"],
                    "line": cls.line,
                    "kind": cls.kind,
                    "fields": [
                        {
                            "name": field.name,
                            "annotation": field.annotation,
                            "line": field.line,
                        }
                        for field in cls.fields
                    ],
                    "enum_values": [ast.literal_eval(value) for value in cls.enum_values],
                }
            )

    ordered: dict[str, list[dict[str, Any]]] = {}
    for name, locations in sorted(result.items()):
        ordered[name] = sorted(
            locations,
            key=lambda item: (item["file"] == "ClientRequest.py", item["file"], item["line"]),
        )
    return ordered


def file_bucket(file_name: str) -> str:
    stem = Path(file_name).stem
    if stem in {"ClientRequest", "ClientNotification", "JSONRPCMessage"}:
        return "entrypoints"
    if stem.startswith("JSONRPC"):
        return "jsonrpc"
    if "Approval" in stem:
        return "approvals"
    if stem.startswith("FuzzyFileSearch"):
        return "fuzzy_search"
    if stem.startswith("McpServerElicitation"):
        return "mcp_elicitation"
    if stem.startswith("DynamicToolCall"):
        return "dynamic_tools"
    if stem.startswith("ChatgptAuthTokensRefresh") or stem.startswith("AttestationGenerate"):
        return "auth_and_attestation"
    return "misc"


def family_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(entry["family"] for entry in entries).items()))


def build_index(files_data: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = class_lookup(files_data)
    raw_main = load_raw_schema_source(RAW_PROTOCOL_SCHEMA, nested_v2=False)
    raw_v2 = load_raw_schema_source(RAW_PROTOCOL_V2_SCHEMA, nested_v2=False)

    request_entries = build_client_requests(files_data, lookup, raw_main, raw_v2)
    notification_entries = build_client_notifications(files_data)
    server_request_entries = build_server_requests(lookup, raw_main, raw_v2)
    server_notification_entries = build_server_notifications(lookup, raw_main, raw_v2)
    file_summaries = build_file_summaries(files_data, request_entries, lookup)
    duplicates = build_duplicates(lookup)

    buckets: dict[str, list[str]] = defaultdict(list)
    for file_data in files_data:
        buckets[file_bucket(file_data["file"])].append(file_data["file"])
    buckets["raw_protocol_schemas"] = sorted([relpath(RAW_PROTOCOL_SCHEMA), relpath(RAW_PROTOCOL_V2_SCHEMA)])

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema_dir": relpath(SCHEMA_DIR),
        "schema_dir_repo_path": repo_relpath(SCHEMA_DIR),
        "request_count_total": len(request_entries),
        "client_request_count_total": len(request_entries),
        "client_notification_count_total": len(notification_entries),
        "server_request_count_total": len(server_request_entries),
        "server_notification_count_total": len(server_notification_entries),
        "progressive_disclosure": {
            "level_0": [
                "Read AGENT_INDEX.md first.",
                "Use `agent_index.json.client_requests`, `server_requests`, or `server_notifications` to map a method to the exact payload model.",
                "Open only the target file and line for the params model or dedicated schema file.",
            ],
            "level_1": [
                "Prefer dedicated standalone files over duplicated inline definitions in ClientRequest.py.",
                "Only open ClientRequest.py for inline-only params models or to inspect the request union wrapper.",
                "When the location points into `json_schema/codex_app_server_protocol*.json`, that payload was indexed directly from the raw aggregate protocol schema rather than a generated Python file.",
            ],
            "level_2": [
                "Drop to raw schema source only after the JSON index points to a specific class.",
            ],
        },
        "protocol_notes": PROTOCOL_NOTES,
        "schema_sources": [
            {
                "file": relpath(RAW_PROTOCOL_SCHEMA),
                "repo_path": repo_relpath(RAW_PROTOCOL_SCHEMA),
                "description": "Aggregate protocol schema containing the client request union, server request union, and notification union.",
            },
            {
                "file": relpath(RAW_PROTOCOL_V2_SCHEMA),
                "repo_path": repo_relpath(RAW_PROTOCOL_V2_SCHEMA),
                "description": "Flattened v2 definitions used for notification payload and response-model lookups.",
            },
        ],
        "file_buckets": {key: sorted(value) for key, value in sorted(buckets.items())},
        "family_counts": family_counts(request_entries),
        "server_request_family_counts": family_counts(server_request_entries),
        "server_notification_family_counts": family_counts(server_notification_entries),
        "client_requests": request_entries,
        "client_notifications": notification_entries,
        "client_request_responses": [
            {
                "method": entry["method"],
                "response_model": entry["response_model"],
                "response_location": entry["response_location"],
            }
            for entry in request_entries
            if entry["response_model"]
        ],
        "server_requests": server_request_entries,
        "server_notifications": server_notification_entries,
        "files": file_summaries,
        "duplicates": duplicates,
        "class_index": build_class_index(files_data),
    }


def render_markdown(index: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Codex Schema Agent Index")
    lines.append("")
    lines.append("This directory contains generated Pydantic models from the codex app-server schema.")
    lines.append("Use this index to avoid opening large union files until you know the exact target type.")
    lines.append("")
    lines.append("## Progressive Disclosure")
    lines.append("")
    for step in index["progressive_disclosure"]["level_0"]:
        lines.append(f"1. {step}")
    lines.append("1. If the type is duplicated, prefer the dedicated standalone file instead of `ClientRequest.py`.")
    lines.append("1. Open `ClientRequest.py` only for inline-only request params or the request union itself.")
    lines.append("1. Open `json_schema/codex_app_server_protocol*.json` only when the index points there for server requests, notifications, or response models with no generated Python file.")
    lines.append("")
    lines.append("## Fast Paths")
    lines.append("")
    lines.append("- Raw JSON-RPC envelope: `JSONRPCMessage.py`, `JSONRPCRequest.py`, `JSONRPCResponse.py`, `JSONRPCError.py`, `JSONRPCNotification.py`.")
    lines.append("- Client-to-server request dispatch: `agent_index.json -> client_requests`.")
    lines.append("- Client request response lookup: `agent_index.json -> client_request_responses`.")
    lines.append("- Server-to-client request dispatch: `agent_index.json -> server_requests`.")
    lines.append("- Server-to-client notification dispatch: `agent_index.json -> server_notifications`.")
    lines.append("- Client-sent notification dispatch: `agent_index.json -> client_notifications`.")
    lines.append("- Exact class fields: `agent_index.json -> class_index[ClassName]`.")
    lines.append("- Approval payloads: files under the `approvals` bucket.")
    lines.append("- Raw aggregate protocol sources: `json_schema/codex_app_server_protocol.schemas.json`, `json_schema/codex_app_server_protocol.v2.schemas.json`.")
    lines.append("- Search/tool payloads: `FuzzyFileSearch*.py`, `DynamicToolCall*.py`, `McpServerElicitation*.py`.")
    lines.append("")
    lines.append("## Protocol Coverage")
    lines.append("")
    lines.append("| Surface | Count | Primary source |")
    lines.append("| --- | ---: | --- |")
    lines.append(f"| Client requests | {index['client_request_count_total']} | `ClientRequest.py` + index metadata |")
    lines.append(f"| Client request responses | {len(index['client_request_responses'])} | raw protocol schemas, with generated file preference when available |")
    lines.append(f"| Server requests | {index['server_request_count_total']} | raw protocol schema unions |")
    lines.append(f"| Server notifications | {index['server_notification_count_total']} | raw protocol schema unions |")
    lines.append(f"| Client notifications | {index['client_notification_count_total']} | `ClientNotification.py` |")
    lines.append("")
    lines.append("## Client Request Families")
    lines.append("")
    lines.append("| Family | Request count |")
    lines.append("| --- | ---: |")
    for family, count in sorted(index["family_counts"].items()):
        lines.append(f"| `{family}` | {count} |")
    lines.append("")
    lines.append("## Server Request Families")
    lines.append("")
    lines.append("| Family | Request count |")
    lines.append("| --- | ---: |")
    for family, count in sorted(index["server_request_family_counts"].items()):
        lines.append(f"| `{family}` | {count} |")
    lines.append("")
    lines.append("## Server Notification Families")
    lines.append("")
    lines.append("| Family | Notification count |")
    lines.append("| --- | ---: |")
    for family, count in sorted(index["server_notification_family_counts"].items()):
        lines.append(f"| `{family}` | {count} |")
    lines.append("")
    lines.append("## File Buckets")
    lines.append("")
    for bucket, files in index["file_buckets"].items():
        joined = ", ".join(f"`{name}`" for name in files)
        lines.append(f"- `{bucket}`: {joined}")
    lines.append("")
    lines.append("## Protocol Notes")
    lines.append("")
    for note in index["protocol_notes"]:
        lines.append(f"- {note}")
    lines.append("")
    lines.append("## Preferred Duplicates")
    lines.append("")
    lines.append("These class names exist in multiple files. Use the preferred location first to minimize context.")
    lines.append("")
    duplicate_rows = index["duplicates"][:12]
    lines.append("| Class | Preferred location | Other locations |")
    lines.append("| --- | --- | --- |")
    for item in duplicate_rows:
        preferred = item["preferred_location"]
        others = [
            f"{loc['file']}:{loc['line']}"
            for loc in item["locations"]
            if loc != preferred
        ]
        lines.append(
            f"| `{item['name']}` | `{preferred['file']}:{preferred['line']}` | {', '.join(f'`{entry}`' for entry in others)} |"
        )
    if len(index["duplicates"]) > len(duplicate_rows):
        lines.append("")
        lines.append(
            f"Full duplicate list: `agent_index.json -> duplicates` ({len(index['duplicates'])} entries)."
        )
    lines.append("")
    lines.append("## High-Value Entry Files")
    lines.append("")
    high_value_files = [
        file_info
        for file_info in index["files"]
        if file_info["file"]
        in {
            "ClientRequest.py",
            "ClientNotification.py",
            "JSONRPCMessage.py",
            "CommandExecutionRequestApprovalParams.py",
            "CommandExecutionRequestApprovalResponse.py",
            "ExecCommandApprovalParams.py",
            "ApplyPatchApprovalParams.py",
            "FuzzyFileSearchParams.py",
            "FuzzyFileSearchResponse.py",
            "DynamicToolCallParams.py",
            "DynamicToolCallResponse.py",
        }
    ]
    lines.append("| File | Top-level class | Notes |")
    lines.append("| --- | --- | --- |")
    for file_info in sorted(high_value_files, key=lambda item: item["file"]):
        note_parts: list[str] = []
        if file_info["used_by_methods"]:
            sample = ", ".join(file_info["used_by_methods"][:3])
            note_parts.append(f"used by {sample}")
        if file_info["has_duplicate_top_level"]:
            note_parts.append("duplicated name; prefer standalone file")
        if not note_parts:
            note_parts.append("standalone schema")
        lines.append(
            f"| `{file_info['file']}` | `{file_info['top_level_class']}` | {'; '.join(note_parts)} |"
        )
    lines.append("")
    lines.append("## Raw Protocol Sources")
    lines.append("")
    lines.append("| File | Purpose |")
    lines.append("| --- | --- |")
    for source in index["schema_sources"]:
        lines.append(f"| `{source['file']}` | {source['description']} |")
    lines.append("")
    lines.append("## Regeneration")
    lines.append("")
    lines.append("```bash")
    lines.append("python src/workflow_agents/runtime/codex_schema/build_agent_index.py")
    lines.append("```")
    lines.append("")
    lines.append("Machine-readable source of truth: `agent_index.json`.")
    return "\n".join(lines) + "\n"


def to_jsonable(index: dict[str, Any]) -> dict[str, Any]:
    return index


def main() -> None:
    files = sorted(path for path in SCHEMA_DIR.glob("*.py") if path.name not in SKIP_FILES)
    files_data = [parse_python_file(path) for path in files]
    index = build_index(files_data)

    OUTPUT_MARKDOWN.write_text(render_markdown(index), encoding="utf-8")
    OUTPUT_JSON.write_text(
        json.dumps(to_jsonable(index), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {relpath(OUTPUT_MARKDOWN)}")
    print(f"Wrote {relpath(OUTPUT_JSON)}")


if __name__ == "__main__":
    main()
