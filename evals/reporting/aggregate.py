from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import CaseAggregate, CaseResult, MetricAggregate, MetricResult, RunSummary


def write_case_result(path: Path, case_result: CaseResult) -> None:
    path.write_text(
        json.dumps(case_result.to_dict(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def write_run_summary(path: Path, summary: RunSummary) -> None:
    path.write_text(
        json.dumps(summary.to_dict(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def build_run_summary(
    *,
    suite_run_id: str,
    case_results: list[CaseResult],
    created_at_utc: str | None = None,
) -> RunSummary:
    latencies = [case_result.wall_time_ms for case_result in case_results]
    costs = [case_result.cost_usd for case_result in case_results]
    tool_counts = [case_result.tool_count for case_result in case_results]
    passed_executions = sum(1 for case_result in case_results if case_result.passed)
    total_executions = len(case_results)
    total_cases = len({case_result.case_id for case_result in case_results})

    ordered_case_results = sorted(
        case_results, key=lambda item: (item.case_id, item.repeat_index)
    )

    return RunSummary(
        suite_run_id=suite_run_id,
        created_at_utc=created_at_utc or _utc_now_iso(),
        total_cases=total_cases,
        total_executions=total_executions,
        passed_executions=passed_executions,
        pass_rate=_safe_ratio(passed_executions, total_executions),
        total_cost_usd=round(sum(costs), 6),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        mean_tool_calls=_mean(tool_counts),
        case_summaries=_build_case_summaries(ordered_case_results),
        case_results=ordered_case_results,
    )


def load_run_summary(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))

    case_results = load_case_results(run_dir)
    summary = build_run_summary(
        suite_run_id=run_dir.name,
        case_results=[case_result_from_dict(item) for item in case_results],
    )
    write_run_summary(summary_path, summary)
    return summary.to_dict()


def load_case_results(run_dir: Path) -> list[dict[str, Any]]:
    evaluations_dir = run_dir / "evaluations"
    if not evaluations_dir.exists():
        raise FileNotFoundError(f"evaluation directory not found: {evaluations_dir}")

    results: list[dict[str, Any]] = []
    for path in sorted(evaluations_dir.glob("*.json")):
        results.append(json.loads(path.read_text(encoding="utf-8")))
    return results


def case_result_from_dict(payload: dict[str, Any]) -> CaseResult:
    return CaseResult(
        case_id=str(payload.get("case_id", "")),
        repeat_index=int(payload.get("repeat_index", 0)),
        passed=bool(payload.get("passed", False)),
        metrics=[
            MetricResult(
                name=str(metric.get("name", "")),
                kind=str(metric.get("kind", "hard")),
                passed=bool(metric.get("passed", False)),
                score=float(metric.get("score", 0.0)),
                reason=str(metric.get("reason", "")),
                details=dict(metric.get("details", {})),
                latency_ms=int(metric.get("latency_ms", 0)),
                cost_usd=float(metric.get("cost_usd", 0.0)),
            )
            for metric in payload.get("metrics", [])
            if isinstance(metric, dict)
        ],
        trace_path=str(payload.get("trace_path", "")),
        evaluation_path=str(payload.get("evaluation_path", "")),
        wall_time_ms=int(payload.get("wall_time_ms", 0)),
        cost_usd=float(payload.get("cost_usd", 0.0)),
        tool_count=int(payload.get("tool_count", 0)),
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _build_case_summaries(case_results: list[CaseResult]) -> list[CaseAggregate]:
    grouped: dict[str, list[CaseResult]] = {}
    for case_result in case_results:
        grouped.setdefault(case_result.case_id, []).append(case_result)

    aggregates: list[CaseAggregate] = []
    for case_id, repeats in sorted(grouped.items()):
        passed_repeats = sum(1 for item in repeats if item.passed)
        metric_groups: dict[str, list[MetricResult]] = {}
        for repeat in repeats:
            for metric in repeat.metrics:
                metric_groups.setdefault(metric.name, []).append(metric)

        metric_aggregates = [
            MetricAggregate(
                name=name,
                passed_repeats=sum(1 for metric in metrics if metric.passed),
                total_repeats=len(metrics),
                mean_score=_mean([metric.score for metric in metrics]),
                min_score=min(metric.score for metric in metrics),
                max_score=max(metric.score for metric in metrics),
            )
            for name, metrics in sorted(metric_groups.items())
        ]
        aggregates.append(
            CaseAggregate(
                case_id=case_id,
                passed_repeats=passed_repeats,
                total_repeats=len(repeats),
                pass_rate=_safe_ratio(passed_repeats, len(repeats)),
                metric_aggregates=metric_aggregates,
            )
        )
    return aggregates


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])

    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])

    lower_value = ordered[lower]
    upper_value = ordered[upper]
    weight = position - lower
    return float(lower_value + (upper_value - lower_value) * weight)


def _utc_now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.isoformat().replace("+00:00", "Z")
