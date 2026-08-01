from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ReuseField = str

@dataclass(slots=True)
class ReusedAgentConfig:
    """复用的具体配置内容字段"""

    model: str = ""
    skills: list[str] = field(default_factory=list)
    mcp: dict[str, Any] = field(default_factory=dict)
    auth: dict[str, Any] = field(default_factory=dict)
    runtime_options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ReusedConfigSnapshot:
    """复用配置的整体记录"""

    agent_type: str
    target_directory: Path
    reused_config: ReusedAgentConfig        # 具体复用的配置
    written_files: list[Path] = field(default_factory=list)
    skipped_fields: list[str] = field(default_factory=list)

def build_reused_agent_config(
    *,
    agent_type: str,
    working_directory: str | Path,
    reuse_fields: tuple[ReuseField, ...] = ("model",),
    home_directory: str | Path | None = None,
    include_home_defaults: bool = True,
) -> ReusedAgentConfig:
    """
    通过参数从指定的配置文件夹构建一套最小可复用的具体配置
    Args:
        agent_type: agent类型
        working_directory: 新的agent配置目录
        [optional] reuse_fields: 哪些配置需要复用
        [optional] home_directory: home目录，用于搜索agent默认配置。默认使用Path.home获取
        [optional] include_home_defaults: 是否将home目录的agent配置加入配置合并列表
    """
    workdir = Path(working_directory).resolve()
    home = Path(home_directory).resolve() if home_directory is not None else Path.home()
    if agent_type == "claude":
        return _load_claude_reused_config(
            workdir=workdir,
            home=home,
            reuse_fields=reuse_fields,
            include_home_defaults=include_home_defaults,
        )
    if agent_type == "claude_sdk":
        return _load_claude_reused_config(
            workdir=workdir,
            home=home,
            reuse_fields=reuse_fields,
            include_home_defaults=include_home_defaults,
        )
    if agent_type in {"codex", "codex_sdk"}:
        return _load_codex_reused_config(
            workdir=workdir,
            home=home,
            reuse_fields=reuse_fields,
            include_home_defaults=include_home_defaults,
        )
    raise ValueError(f"unsupported agent_type for config reuse: {agent_type}")


def apply_reused_agent_config(
    *,
    reused_config: ReusedAgentConfig,
    reuse_fields: tuple[ReuseField, ...] = ("model",),
    **kwargs: Any,
) -> dict[str, Any]:
    """Apply one reused-config snapshot onto AgentNodeConfig constructor kwargs."""
    payload = dict(kwargs)
    if not payload.get("model"):
        payload["model"] = reused_config.model

    runtime_options = dict(reused_config.runtime_options)
    if reused_config.skills:
        runtime_options.setdefault("reused_skills", list(reused_config.skills))
    if reused_config.mcp:
        runtime_options.setdefault("reused_mcp", dict(reused_config.mcp))
    if "auth" in reuse_fields and reused_config.auth:
        runtime_options.setdefault("reused_auth", dict(reused_config.auth))
    runtime_options.update(dict(payload.get("runtime_options") or {}))
    payload["runtime_options"] = runtime_options
    return payload


def write_reused_agent_config(
    *,
    agent_type: str,
    target_directory: str | Path,
    reused_config: ReusedAgentConfig,
    overwrite: bool = False,
) -> ReusedConfigSnapshot:
    """
    根据参数构建复用配置并写入到目标配置文件夹
    Args:
        agent_type: agent类型
        source_working_directory: 新的agent配置目录
        [optional] reuse_fields: 哪些配置需要复用
        [optional] home_directory: home目录，用于搜索agent默认配置。默认使用Path.home获取
        [optional] include_home_defaults: 是否将home目录的agent配置加入配置合并列表
        [optional] overwrite: 是否覆盖原有配置
    """
    target_root = Path(target_directory).resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    if agent_type in {"claude", "claude_sdk"}:
        written_files = _write_claude_snapshot(target_root, reused_config, overwrite=overwrite)
        skipped_fields: list[str] = []
    elif agent_type in {"codex", "codex_sdk"}:
        written_files, skipped_fields = _write_codex_snapshot(target_root, reused_config, overwrite=overwrite)
    else:
        raise ValueError(f"unsupported agent_type for config materialization: {agent_type}")

    return ReusedConfigSnapshot(
        agent_type=agent_type,
        target_directory=target_root,
        reused_config=reused_config,
        written_files=written_files,
        skipped_fields=skipped_fields,
    )


def _load_claude_reused_config(
    *,
    workdir: Path,
    home: Path,
    reuse_fields: tuple[ReuseField, ...],
    include_home_defaults: bool,
) -> ReusedAgentConfig:
    """
    构建claude复用配置
    会合并下列几个配置，后面的会覆盖前面的
      * 若指定了include_home_defaults会合并home/.claude下的配置
      * workdir/.claude 的settings.json和settings.local.json
    根据情况保留下列几个关键字的配置： model skills mcp
    """
    project_local = workdir / ".claude" / "settings.local.json"
    project_settings = workdir / ".claude" / "settings.json"
    user_settings = home / ".claude" / "settings.json"

    merged: dict[str, Any] = {}
    candidate_paths = []
    if include_home_defaults:
        candidate_paths.append(user_settings)
    candidate_paths.extend([project_settings, project_local])
    for path in candidate_paths:
        merged.update(_read_json_object(path))

    model = str(merged.get("model", "") or "") if "model" in reuse_fields else ""
    skills = list(merged.get("skills", []) or []) if "skills" in reuse_fields and isinstance(merged.get("skills"), list) else []
    mcp = dict(merged.get("mcp", {}) or {}) if "mcp" in reuse_fields and isinstance(merged.get("mcp"), dict) else {}
    return ReusedAgentConfig(
        model=model,
        skills=[str(item) for item in skills],
        mcp=mcp,
        metadata={
            "source_kind": "claude_settings",
            "reused_fields": list(reuse_fields),
            "sources": [str(path) for path in candidate_paths if path.exists()],
        },
    )


def _load_codex_reused_config(
    *,
    workdir: Path,
    home: Path,
    reuse_fields: tuple[ReuseField, ...],
    include_home_defaults: bool,
) -> ReusedAgentConfig:
    """
    构建codex复用配置
    会合并下列几个配置，后面的会覆盖前面的
      * 若指定了include_home_defaults会合并home/.codex下的配置
      * workdir/.codex 下的config.toml和auth.json
    根据情况保留下列几个关键字的配置： model base_url model_reasoning_effort skills mcp
    """
    project_config = workdir / ".codex" / "config.toml"
    project_auth = workdir / ".codex" / "auth.json"
    user_config = home / ".codex" / "config.toml"
    user_auth = home / ".codex" / "auth.json"

    merged: dict[str, Any] = {}
    merged_auth: dict[str, Any] = {}
    candidate_paths = []
    auth_candidate_paths: list[Path] = []
    if include_home_defaults:
        candidate_paths.append(user_config)
    candidate_paths.append(project_config)
    for path in candidate_paths:
        merged.update(_read_simple_toml(path))
    if "auth" in reuse_fields:
        if include_home_defaults:
            auth_candidate_paths.append(user_auth)
        auth_candidate_paths.append(project_auth)
        for path in auth_candidate_paths:
            merged_auth.update(_read_json_object(path))

    model = str(merged.get("model", "") or "") if "model" in reuse_fields else ""
    runtime_options: dict[str, Any] = {}
    reused_base_url = _extract_codex_base_url(merged) if "model" in reuse_fields else ""
    if reused_base_url:
        runtime_options["reused_base_url"] = reused_base_url
    if "model" in reuse_fields and "model_reasoning_effort" in merged:
        runtime_options["reused_model_reasoning_effort"] = merged["model_reasoning_effort"]
    skills = list(merged.get("skills", []) or []) if "skills" in reuse_fields and isinstance(merged.get("skills"), list) else []
    mcp = dict(merged.get("mcp", {}) or {}) if "mcp" in reuse_fields and isinstance(merged.get("mcp"), dict) else {}
    return ReusedAgentConfig(
        model=model,
        skills=[str(item) for item in skills],
        mcp=mcp,
        auth=merged_auth,
        runtime_options=runtime_options,
        metadata={
            "source_kind": "codex_config_toml",
            "reused_fields": list(reuse_fields),
            "sources": [str(path) for path in candidate_paths if path.exists()],
            "auth_sources": [str(path) for path in auth_candidate_paths if path.exists()],
        },
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object file, returning an empty object when missing or invalid."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_codex_base_url(payload: dict[str, Any]) -> str:
    """Extract a usable Codex base_url from either top-level or provider-scoped config."""
    direct_base_url = payload.get("base_url")
    if isinstance(direct_base_url, str) and direct_base_url:
        return direct_base_url

    provider_name = str(payload.get("model_provider", "") or "").strip()
    if not provider_name:
        return ""

    model_providers = payload.get("model_providers")
    if not isinstance(model_providers, dict):
        return ""

    provider_payload = model_providers.get(provider_name)
    if not isinstance(provider_payload, dict):
        return ""

    provider_base_url = provider_payload.get("base_url")
    return str(provider_base_url or "").strip()


def _read_simple_toml(path: Path) -> dict[str, Any]:
    """Read a flat TOML key/value file using stdlib support when available."""
    if not path.exists():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError:
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_claude_snapshot(root: Path, reused: ReusedAgentConfig, *, overwrite: bool) -> list[Path]:
    """
    将当前的复用配置写入claude配置目录
    """
    payload: dict[str, Any] = {}
    if reused.model:
        payload["model"] = reused.model
    if reused.skills:
        payload["skills"] = list(reused.skills)
    if reused.mcp:
        payload["mcp"] = dict(reused.mcp)
    if not payload:
        return []

    config_path = root / ".claude" / "settings.json"
    if config_path.exists() and not overwrite:
        return []
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return [config_path]


def _write_codex_snapshot(root: Path, reused: ReusedAgentConfig, *, overwrite: bool) -> tuple[list[Path], list[str]]:
    """
    将当前的复用配置写入codex配置目录
    """
    payload: dict[str, Any] = {}
    if reused.model:
        payload["model"] = reused.model
    if "reused_base_url" in reused.runtime_options:
        payload["base_url"] = reused.runtime_options["reused_base_url"]
    if "reused_model_reasoning_effort" in reused.runtime_options:
        payload["model_reasoning_effort"] = reused.runtime_options["reused_model_reasoning_effort"]
    if reused.skills:
        payload["skills"] = list(reused.skills)
    if reused.mcp:
        payload["mcp"] = dict(reused.mcp)
    written_files: list[Path] = []
    skipped_fields: list[str] = []

    config_path = root / ".codex" / "config.toml"
    if payload and (overwrite or not config_path.exists()):
        rendered, skipped_fields = _render_toml_document(payload)
        if rendered.strip():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(rendered, encoding="utf-8")
            written_files.append(config_path.resolve())

    auth_path = root / ".codex" / "auth.json"
    if reused.auth and (overwrite or not auth_path.exists()):
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(reused.auth, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        written_files.append(auth_path.resolve())

    return written_files, skipped_fields


def _render_toml_document(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Render a minimal TOML document and report unsupported field paths."""
    lines: list[str] = []
    skipped_fields: list[str] = []

    for key, value in payload.items():
        if isinstance(value, dict):
            continue
        rendered_value = _render_toml_value(value)
        if rendered_value is None:
            skipped_fields.append(key)
            continue
        lines.append(f"{key} = {rendered_value}")

    nested_items = [(key, value) for key, value in payload.items() if isinstance(value, dict)]
    for index, (key, value) in enumerate(nested_items):
        if lines or index > 0:
            lines.append("")
        lines.extend(_render_toml_table(key, value, skipped_fields))

    return ("\n".join(lines) + "\n") if lines else "", skipped_fields


def _render_toml_table(table_name: str, payload: dict[str, Any], skipped_fields: list[str]) -> list[str]:
    """Render one TOML table, recursing into nested dict values."""
    lines = [f"[{table_name}]"]
    nested_tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            nested_tables.append((key, value))
            continue
        rendered_value = _render_toml_value(value)
        if rendered_value is None:
            skipped_fields.append(f"{table_name}.{key}")
            continue
        lines.append(f"{key} = {rendered_value}")

    for key, value in nested_tables:
        lines.append("")
        lines.extend(_render_toml_table(f"{table_name}.{key}", value, skipped_fields))
    return lines


def _render_toml_value(value: Any) -> str | None:
    """Render one TOML scalar or scalar list value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, list):
        rendered_items: list[str] = []
        for item in value:
            rendered_item = _render_toml_value(item)
            if rendered_item is None or isinstance(item, (dict, list)):
                return None
            rendered_items.append(rendered_item)
        return "[" + ", ".join(rendered_items) + "]"
    return None
