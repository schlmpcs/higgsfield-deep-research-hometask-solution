from __future__ import annotations

from ..models import MetricResult
from .registry import MetricContext, register_metric_collector


@register_metric_collector
def collect_budget_metrics(context: MetricContext) -> list[MetricResult]:
    results: list[MetricResult] = []
    budgets = context.case.budgets
    trace = context.trace

    if budgets.max_tool_calls is not None:
        actual = trace.normalized.tool_count
        passed = actual <= budgets.max_tool_calls
        results.append(
            MetricResult(
                name="budget_tool_calls",
                kind="hard",
                passed=passed,
                score=1.0 if passed else 0.0,
                reason=(
                    f"Tool count {actual} {'<=' if passed else '>'} "
                    f"budget {budgets.max_tool_calls}."
                ),
                details={"budget": budgets.max_tool_calls, "actual": actual},
            )
        )

    if budgets.max_latency_ms is not None:
        actual = trace.normalized.wall_time_ms
        passed = actual <= budgets.max_latency_ms
        results.append(
            MetricResult(
                name="budget_latency_ms",
                kind="hard",
                passed=passed,
                score=1.0 if passed else 0.0,
                reason=(
                    f"Wall time {actual}ms {'<=' if passed else '>'} "
                    f"budget {budgets.max_latency_ms}ms."
                ),
                details={"budget_ms": budgets.max_latency_ms, "actual_ms": actual},
            )
        )

    return results
