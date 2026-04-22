from __future__ import annotations

from pathlib import Path
from typing import Any

from .aggregate import load_run_summary


def load_diff(run_dir: Path, baseline_dir: Path) -> dict[str, Any]:
    current = load_run_summary(run_dir)
    baseline = load_run_summary(baseline_dir)
    return build_diff(current=current, baseline=baseline)


def build_diff(*, current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    current_results = _index_case_results(current.get("case_results", []))
    baseline_results = _index_case_results(baseline.get("case_results", []))
    shared_keys = sorted(set(current_results) & set(baseline_results))

    newly_failing: list[str] = []
    newly_passing: list[str] = []
    metric_regressions: list[dict] = []
    for key in shared_keys:
        current_passed = bool(current_results[key].get("passed", False))
        baseline_passed = bool(baseline_results[key].get("passed", False))
        if baseline_passed and not current_passed:
            newly_failing.append(key)
        if not baseline_passed and current_passed:
            newly_passing.append(key)

        cur_metrics = {m["name"]: m["passed"] for m in current_results[key].get("metrics", [])}
        base_metrics = {m["name"]: m["passed"] for m in baseline_results[key].get("metrics", [])}
        for metric_name in set(cur_metrics) & set(base_metrics):
            if base_metrics[metric_name] and not cur_metrics[metric_name]:
                metric_regressions.append({"execution": key, "metric": metric_name})

    return {
        "run_id": str(current.get("suite_run_id", "")),
        "baseline_run_id": str(baseline.get("suite_run_id", "")),
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
        "metric_regressions": metric_regressions,
        "pass_rate_delta": float(current.get("pass_rate", 0.0))
        - float(baseline.get("pass_rate", 0.0)),
        "p50_latency_delta_ms": float(current.get("p50_latency_ms", 0.0))
        - float(baseline.get("p50_latency_ms", 0.0)),
        "p95_latency_delta_ms": float(current.get("p95_latency_ms", 0.0))
        - float(baseline.get("p95_latency_ms", 0.0)),
        "cost_delta_usd": float(current.get("total_cost_usd", 0.0))
        - float(baseline.get("total_cost_usd", 0.0)),
    }


def _index_case_results(case_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in case_results:
        case_id = str(item.get("case_id", ""))
        repeat_index = int(item.get("repeat_index", 0))
        indexed[_case_key(case_id, repeat_index)] = item
    return indexed


def _case_key(case_id: str, repeat_index: int) -> str:
    return f"{case_id} r{repeat_index}"
