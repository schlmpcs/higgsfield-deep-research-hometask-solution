from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import BudgetConfig, HardAssertionSpec, JudgeMetricSpec, TestCase

DEFAULT_CASES_DIR = Path(__file__).resolve().parent / "cases"


class CaseLoadError(ValueError):
    """Raised when a YAML case file cannot be parsed into a TestCase."""


def load_cases(case_dir: Path | None = None) -> list[TestCase]:
    case_dir = case_dir or DEFAULT_CASES_DIR
    if not case_dir.exists():
        raise CaseLoadError(f"case directory does not exist: {case_dir}")
    if not case_dir.is_dir():
        raise CaseLoadError(f"case path is not a directory: {case_dir}")

    cases: list[TestCase] = []
    seen_ids: set[str] = set()

    case_paths = sorted(
        {
            *case_dir.glob("*.yaml"),
            *case_dir.glob("*.yml"),
            *case_dir.glob("*.json"),
        }
    )

    for path in case_paths:
        case = load_case(path)
        if case.id in seen_ids:
            raise CaseLoadError(f"duplicate case id '{case.id}' in {path}")
        seen_ids.add(case.id)
        cases.append(case)

    return cases


def load_case(path: Path) -> TestCase:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaseLoadError(f"could not read case file {path}: {exc}") from exc

    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(text)
        else:
            raw = yaml.safe_load(text)
    except json.JSONDecodeError as exc:
        raise CaseLoadError(f"invalid JSON in {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CaseLoadError(f"invalid YAML in {path}: {exc}") from exc

    return parse_case(raw, path)


def parse_case(raw: Any, path: Path) -> TestCase:
    if not isinstance(raw, dict):
        raise CaseLoadError(f"{path} must contain a top-level mapping")

    expected_behavior_raw = _optional_mapping(
        raw.get("expected_behavior"), "expected_behavior", path
    )
    budgets_raw = _optional_mapping(raw.get("budgets"), "budgets", path)
    hard_assertions_raw = _merge_lists(
        _optional_list(raw.get("hard_assertions"), "hard_assertions", path),
        _optional_list(
            expected_behavior_raw.get("hard_assertions"),
            "expected_behavior.hard_assertions",
            path,
        ),
    )
    judge_metrics_raw = _merge_lists(
        _optional_list(raw.get("judge_metrics"), "judge_metrics", path),
        _optional_list(
            expected_behavior_raw.get("judge_metrics"),
            "expected_behavior.judge_metrics",
            path,
        ),
    )

    return TestCase(
        id=_required_string(raw, "id", path),
        input=_required_string(raw, "input", path),
        description=_optional_string(raw.get("description"), "description", path, ""),
        tags=_string_list(raw.get("tags"), "tags", path),
        budgets=BudgetConfig(
            max_tool_calls=_optional_int(
                budgets_raw.get("max_tool_calls"),
                "budgets.max_tool_calls",
                path,
            ),
            max_latency_ms=_optional_int(
                budgets_raw.get("max_latency_ms"),
                "budgets.max_latency_ms",
                path,
            ),
        ),
        hard_assertions=[
            HardAssertionSpec(
                type=_required_string(item, "type", path, prefix="hard_assertions[]"),
                value=item.get("value"),
                match=_optional_string(item.get("match"), "match", path),
            )
            for item in (
                _required_mapping(item, "hard_assertions[]", path)
                for item in hard_assertions_raw
            )
        ],
        judge_metrics=[
            JudgeMetricSpec(
                name=_required_string(item, "name", path, prefix="judge_metrics[]"),
                rubric_file=_required_string(
                    item,
                    "rubric_file",
                    path,
                    prefix="judge_metrics[]",
                ),
                threshold=_optional_float(
                    item.get("threshold"),
                    "judge_metrics[].threshold",
                    path,
                    0.8,
                ),
            )
            for item in (
                _required_mapping(item, "judge_metrics[]", path)
                for item in judge_metrics_raw
            )
        ],
        source_path=str(path.resolve()),
    )


def _required_mapping(value: Any, label: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaseLoadError(f"{path}: {label} must be a mapping")
    return value


def _optional_mapping(value: Any, label: str, path: Path) -> dict[str, Any]:
    if value is None:
        return {}
    return _required_mapping(value, label, path)


def _optional_list(value: Any, label: str, path: Path) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CaseLoadError(f"{path}: {label} must be a list")
    return value


def _merge_lists(*values: list[Any]) -> list[Any]:
    merged: list[Any] = []
    for value in values:
        merged.extend(value)
    return merged


def _required_string(
    value: dict[str, Any], key: str, path: Path, prefix: str | None = None
) -> str:
    if key not in value or value[key] is None:
        label = f"{prefix}.{key}" if prefix else key
        raise CaseLoadError(f"{path}: missing required field '{label}'")
    return _optional_string(value[key], key, path)


def _optional_string(
    value: Any, label: str, path: Path, default: str | None = None
) -> str | None:
    if value is None:
        return default
    if not isinstance(value, str):
        raise CaseLoadError(f"{path}: {label} must be a string")
    return value


def _string_list(value: Any, label: str, path: Path) -> list[str]:
    raw_items = _optional_list(value, label, path)
    items: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            raise CaseLoadError(f"{path}: {label} entries must be strings")
        items.append(item)
    return items


def _optional_int(value: Any, label: str, path: Path) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise CaseLoadError(f"{path}: {label} must be an integer")
    return value


def _optional_float(value: Any, label: str, path: Path, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise CaseLoadError(f"{path}: {label} must be numeric")
    return float(value)
