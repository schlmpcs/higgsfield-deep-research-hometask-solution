from __future__ import annotations

import time

from ..judge_client import JudgeClient, load_rubric
from ..models import JudgeMetricSpec, MetricResult, TestCase
from .registry import MetricContext, register_metric_collector


@register_metric_collector
def collect_judge_metrics(context: MetricContext) -> list[MetricResult]:
    case = context.case
    if not case.judge_metrics:
        return []

    client = (
        JudgeClient(model=context.judge_model, cache_dir=context.judge_cache_dir)
        if context.judge_model
        else JudgeClient(cache_dir=context.judge_cache_dir)
    )
    return [
        evaluate_judge_metric(spec=spec, client=client, case=case, context=context)
        for spec in case.judge_metrics
    ]


def evaluate_judge_metric(
    *,
    spec: JudgeMetricSpec,
    client: JudgeClient,
    case: TestCase,
    context: MetricContext,
) -> MetricResult:
    started_at = time.perf_counter()
    try:
        rubric_path, rubric_text = load_rubric(spec.rubric_file)
        artifact = client.score_trace(
            raw_trace=context.raw_trace,
            trace_path=context.raw_trace_path,
            rubric_path=rubric_path,
            rubric_text=rubric_text,
            case_id=case.id,
            case_description=case.description,
            metric_name=spec.name,
        )
        passed = artifact.score.passed and artifact.score.score >= spec.threshold
        return MetricResult(
            name=spec.name,
            kind="judge",
            passed=passed,
            score=artifact.score.score,
            reason=artifact.score.reason,
            details={
                "threshold": spec.threshold,
                "judge_passed": artifact.score.passed,
                "evidence": artifact.score.evidence,
                "rubric_path": str(rubric_path.resolve()),
                "artifact_path": artifact.artifact_path,
                "cache_hit": artifact.cache_hit,
            },
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            cost_usd=artifact.cost_usd,
        )
    except Exception as exc:
        return MetricResult(
            name=spec.name,
            kind="judge",
            passed=False,
            score=0.0,
            reason=f"Judge metric failed to run: {exc}",
            details={"threshold": spec.threshold},
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )
