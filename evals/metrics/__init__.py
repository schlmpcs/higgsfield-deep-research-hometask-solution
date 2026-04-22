from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import CaseResult, TestCase, TraceRecord
from . import budgets as _budgets  # noqa: F401
from . import hard_assertions as _hard_assertions  # noqa: F401
from . import judge_metrics as _judge_metrics  # noqa: F401
from .hard_assertions import evaluate_hard_assertion
from .judge_metrics import evaluate_judge_metric
from .registry import MetricContext, iter_metric_collectors


def evaluate_case(
    *,
    case: TestCase,
    trace: TraceRecord,
    raw_trace: dict[str, Any],
    raw_trace_path: Path,
    evaluation_path: Path,
    judge_cache_dir: Path,
    judge_model: str | None = None,
) -> CaseResult:
    context = MetricContext(
        case=case,
        trace=trace,
        raw_trace=raw_trace,
        raw_trace_path=raw_trace_path,
        evaluation_path=evaluation_path,
        judge_cache_dir=judge_cache_dir,
        judge_model=judge_model,
    )
    metrics = [
        metric
        for collector in iter_metric_collectors()
        for metric in collector(context)
    ]

    return CaseResult(
        case_id=case.id,
        repeat_index=trace.repeat_index,
        passed=all(metric.passed for metric in metrics),
        metrics=metrics,
        trace_path=str(raw_trace_path.resolve()),
        evaluation_path=str(evaluation_path.resolve()),
        wall_time_ms=trace.normalized.wall_time_ms,
        cost_usd=trace.normalized.cost_usd,
        tool_count=trace.normalized.tool_count,
    )


__all__ = ["evaluate_case", "evaluate_judge_metric", "evaluate_hard_assertion"]
