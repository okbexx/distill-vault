"""JSON Schema loading and vault object validation."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .snapshot import VaultObject, VaultSnapshot
from .vault_semantics import is_raw_source


@dataclass(frozen=True)
class SchemaIssue:
    path: str
    message: str
    field: str | None
    severity: str = "error"
    rule: str = "schema-validation"

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "file": self.path,
            "field": self.field,
        }


def resolve_schema_path(vault_root: Path | str, config: dict) -> Path | None:
    configured = config.get("schema", {}).get("path")
    if not configured:
        return None
    path = (Path(vault_root).expanduser().resolve() / str(configured)).resolve()
    root = Path(vault_root).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"schema path escapes vault root: {configured}")
    return path


def load_object_schema(vault_root: Path | str, config: dict) -> dict[str, Any] | None:
    path = resolve_schema_path(vault_root, config)
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"object schema does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return payload


def validate_object(obj: VaultObject, schema: dict[str, Any]) -> list[SchemaIssue]:
    validator = Draft202012Validator(schema)
    issues = []
    instance = _json_instance(dict(obj.frontmatter))
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        field = ".".join(str(part) for part in error.path) or None
        issues.append(SchemaIssue(
            path=obj.path,
            field=field,
            message=f"Schema validation failed{f' at {field}' if field else ''}: {error.message}",
        ))
    return issues


def _json_instance(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_instance(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_instance(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def validate_snapshot(
    snapshot: VaultSnapshot,
    config: dict,
) -> list[SchemaIssue]:
    schema = load_object_schema(snapshot.root, config)
    if schema is None:
        return []
    issues = []
    for obj in snapshot.objects:
        if is_raw_source(obj.frontmatter):
            continue
        include_globs = config.get("schema", {}).get("include_globs") or []
        if include_globs and not any(fnmatch.fnmatchcase(obj.path, pattern) for pattern in include_globs):
            continue
        if not include_globs and obj.type in {"unknown", "skill_spec"} and obj.path.startswith("系统/"):
            continue
        issues.extend(validate_object(obj, schema))
    return issues
