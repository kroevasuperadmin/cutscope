from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
from .models import Shot


REQUIRED_SHOT_FIELDS = {
    "id",
    "prompt",
    "expected_duration_seconds",
    "character_ids",
    "max_attempts",
    "budget_ceiling_usd",
}

OPTIONAL_SHOT_FIELDS = {"reference_image_path", "difficulty"}


def load_shots(path: Path) -> list[Shot]:
    if not path.exists():
        raise ConfigurationError(f"Shot file not found: {path}")
    document = _parse_yaml_subset(path.read_text(encoding="utf-8"), path)
    if set(document) != {"shots"} or not isinstance(document["shots"], list):
        raise ConfigurationError(f"{path}: expected one top-level 'shots:' list.")
    shots = [_make_shot(item, path.parent, index + 1) for index, item in enumerate(document["shots"])]
    ids = [shot.id for shot in shots]
    if len(ids) != len(set(ids)):
        raise ConfigurationError(f"{path}: shot ids must be unique.")
    return shots


def _make_shot(data: Any, base_dir: Path, item_number: int) -> Shot:
    if not isinstance(data, dict):
        raise ConfigurationError(f"Shot {item_number} must be a mapping.")
    missing = REQUIRED_SHOT_FIELDS - set(data)
    unexpected = set(data) - REQUIRED_SHOT_FIELDS - OPTIONAL_SHOT_FIELDS
    if missing:
        raise ConfigurationError(f"Shot {item_number} missing fields: {', '.join(sorted(missing))}")
    if unexpected:
        raise ConfigurationError(f"Shot {item_number} has unknown fields: {', '.join(sorted(unexpected))}")
    try:
        reference_value = data.get("reference_image_path")
        if reference_value is not None and not isinstance(reference_value, str):
            raise ValueError("reference_image_path must be a path string or null")
        difficulty = data.get("difficulty")
        if difficulty is not None and (not isinstance(difficulty, str) or not difficulty.strip()):
            raise ValueError("difficulty must be a non-empty string or null")
        reference_path = base_dir / reference_value if reference_value else None
        character_ids = data["character_ids"]
        if not isinstance(character_ids, list) or not all(isinstance(item, str) and item for item in character_ids):
            raise ValueError("character_ids must be a list of non-empty strings")
        return Shot(
            id=_as_nonempty_string(data["id"], "id"),
            prompt=_as_nonempty_string(data["prompt"], "prompt"),
            reference_image_path=reference_path,
            expected_duration_seconds=_as_int(data["expected_duration_seconds"], "expected_duration_seconds"),
            character_ids=tuple(character_ids),
            max_attempts=_as_int(data["max_attempts"], "max_attempts"),
            budget_ceiling_usd=Decimal(str(data["budget_ceiling_usd"])),
            difficulty=difficulty,
        )
    except (InvalidOperation, ValueError) as exc:
        raise ConfigurationError(f"Shot {item_number}: {exc}") from exc


def _as_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _parse_yaml_subset(text: str, path: Path) -> dict[str, list[dict[str, Any]]]:
    """Parse the deliberately small, documented YAML shape without PyYAML.

    JSON is accepted too because it is valid YAML. The YAML form supports a top-level
    shots list, mapping items, and inline scalar lists such as [mara, noa].
    """
    try:
        parsed_json = json.loads(text)
    except json.JSONDecodeError:
        parsed_json = None
    if isinstance(parsed_json, dict):
        return parsed_json

    lines: list[tuple[int, str, int]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        without_comment = raw.split("#", 1)[0].rstrip()
        if not without_comment.strip():
            continue
        indentation = len(without_comment) - len(without_comment.lstrip(" "))
        if "\t" in without_comment[: len(without_comment) - len(without_comment.lstrip())]:
            raise ConfigurationError(f"{path}:{line_number}: tabs are not supported.")
        lines.append((line_number, without_comment.strip(), indentation))

    if not lines or lines[0][1] != "shots:" or lines[0][2] != 0:
        raise ConfigurationError(f"{path}: expected top-level 'shots:'.")

    shots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    line_index = 1
    while line_index < len(lines):
        line_number, content, indent = lines[line_index]
        if indent == 2 and content.startswith("- "):
            current = {}
            shots.append(current)
            key, value = _split_mapping(content[2:], path, line_number)
            current[key] = _parse_scalar(value, path, line_number)
        elif indent == 4 and current is not None:
            key, value = _split_mapping(content, path, line_number)
            if value.startswith('"'):
                while True:
                    try:
                        json.loads(value)
                        break
                    except json.JSONDecodeError:
                        line_index += 1
                        if line_index >= len(lines) or lines[line_index][2] <= indent:
                            raise ConfigurationError(f"{path}:{line_number}: invalid quoted string.") from None
                        value += " " + lines[line_index][1]
            current[key] = _parse_scalar(value, path, line_number)
        else:
            raise ConfigurationError(
                f"{path}:{line_number}: use two spaces for a shot and four for its fields."
            )
        line_index += 1
    return {"shots": shots}


def _split_mapping(content: str, path: Path, line_number: int) -> tuple[str, str]:
    if ":" not in content:
        raise ConfigurationError(f"{path}:{line_number}: expected key: value.")
    key, value = content.split(":", 1)
    if not key.strip() or not value.strip():
        raise ConfigurationError(f"{path}:{line_number}: expected non-empty key and value.")
    return key.strip(), value.strip()


def _parse_scalar(value: str, path: Path, line_number: int) -> Any:
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        return [] if not body else [_parse_scalar(item.strip(), path, line_number) for item in body.split(",")]
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"{path}:{line_number}: invalid quoted string.") from exc
        if not isinstance(parsed, str):
            raise ConfigurationError(f"{path}:{line_number}: expected a string.")
        return parsed
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value
