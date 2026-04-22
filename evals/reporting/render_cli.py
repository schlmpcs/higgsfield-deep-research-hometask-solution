from __future__ import annotations

from typing import Any


def render_run_summary(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    for case_result in summary.get("case_results", []):
        status = "PASS" if case_result.get("passed") else "FAIL"
        case_id = str(case_result.get("case_id", ""))
        repeat_index = int(case_result.get("repeat_index", 0))
        wall_time_ms = int(case_result.get("wall_time_ms", 0))
        cost_usd = float(case_result.get("cost_usd", 0.0))
        lines.append(
            f"{status} {case_id} r{repeat_index}  "
            f"{wall_time_ms / 1000:.1f}s  ${cost_usd:.4f}"
        )

        for metric in case_result.get("metrics", []):
            if metric.get("passed"):
                continue
            lines.append(f"  - {metric.get('name')}: {metric.get('reason')}")

    lines.append(
        "Summary: "
        f"{int(summary.get('passed_executions', 0))}/{int(summary.get('total_executions', 0))} passed "
        f"({float(summary.get('pass_rate', 0.0)):.0%}), "
        f"cost=${float(summary.get('total_cost_usd', 0.0)):.4f}, "
        f"p50={float(summary.get('p50_latency_ms', 0.0)):.0f}ms, "
        f"p95={float(summary.get('p95_latency_ms', 0.0)):.0f}ms, "
        f"mean_tool_calls={float(summary.get('mean_tool_calls', 0.0)):.2f}"
    )

    case_summaries = summary.get("case_summaries", [])
    flaky_cases = [item for item in case_summaries if int(item.get("total_repeats", 0)) > 1]
    if flaky_cases:
        lines.append("Repeat Summary:")
        for case_summary in flaky_cases:
            lines.append(
                f"- {case_summary.get('case_id')}: "
                f"{int(case_summary.get('passed_repeats', 0))}/"
                f"{int(case_summary.get('total_repeats', 0))} passed"
            )
            metric_aggregates = case_summary.get("metric_aggregates", [])
            for metric in metric_aggregates:
                lines.append(
                    "  "
                    f"{metric.get('name')}: "
                    f"{int(metric.get('passed_repeats', 0))}/"
                    f"{int(metric.get('total_repeats', 0))} pass, "
                    f"score_mean={float(metric.get('mean_score', 0.0)):.2f}, "
                    f"range=[{float(metric.get('min_score', 0.0)):.2f}, "
                    f"{float(metric.get('max_score', 0.0)):.2f}]"
                )
    return "\n".join(lines)


def render_diff(diff: dict[str, Any]) -> str:
    lines: list[str] = [
        f"Diff {diff.get('run_id')} vs {diff.get('baseline_run_id')}",
    ]

    newly_failing = diff.get("newly_failing", [])
    if newly_failing:
        lines.append("Newly failing:")
        for item in newly_failing:
            lines.append(f"- {item}")

    newly_passing = diff.get("newly_passing", [])
    if newly_passing:
        lines.append("Newly passing:")
        for item in newly_passing:
            lines.append(f"- {item}")

    metric_regressions = diff.get("metric_regressions", [])
    if metric_regressions:
        lines.append("Metric regressions (case still passes overall):")
        for item in metric_regressions:
            lines.append(f"- {item['execution']}: {item['metric']}")

    if not newly_failing and not newly_passing and not metric_regressions:
        lines.append("No status changes.")

    lines.append(
        "Deltas: "
        f"pass_rate={_format_percent_delta(float(diff.get('pass_rate_delta', 0.0)))}, "
        f"p50={_format_ms_delta(float(diff.get('p50_latency_delta_ms', 0.0)))}, "
        f"p95={_format_ms_delta(float(diff.get('p95_latency_delta_ms', 0.0)))}, "
        f"cost={_format_currency_delta(float(diff.get('cost_delta_usd', 0.0)))}"
    )
    return "\n".join(lines)


def _format_percent_delta(value: float) -> str:
    return f"{value:+.0%}"


def _format_ms_delta(value: float) -> str:
    return f"{value:+.0f}ms"


def _format_currency_delta(value: float) -> str:
    return f"{value:+.4f} USD"
