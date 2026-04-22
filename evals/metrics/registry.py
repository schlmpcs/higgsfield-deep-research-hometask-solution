from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import HardAssertionSpec, MetricResult, TestCase, TraceRecord


@dataclass(slots=True)
class MetricContext:
    case: TestCase
    trace: TraceRecord
    raw_trace: dict[str, Any]
    raw_trace_path: Path
    evaluation_path: Path
    judge_cache_dir: Path
    judge_model: str | None = None


CaseMetricCollector = Callable[[MetricContext], list[MetricResult]]
HardAssertionEvaluator = Callable[[HardAssertionSpec, TraceRecord], MetricResult]

_CASE_METRIC_COLLECTORS: list[CaseMetricCollector] = []
_HARD_ASSERTION_EVALUATORS: dict[str, HardAssertionEvaluator] = {}


def register_metric_collector(collector: CaseMetricCollector) -> CaseMetricCollector:
    _CASE_METRIC_COLLECTORS.append(collector)
    return collector


def iter_metric_collectors() -> tuple[CaseMetricCollector, ...]:
    return tuple(_CASE_METRIC_COLLECTORS)


def register_hard_assertion(
    name: str,
) -> Callable[[HardAssertionEvaluator], HardAssertionEvaluator]:
    def decorator(evaluator: HardAssertionEvaluator) -> HardAssertionEvaluator:
        _HARD_ASSERTION_EVALUATORS[name] = evaluator
        return evaluator

    return decorator


def get_hard_assertion_evaluator(name: str) -> HardAssertionEvaluator | None:
    return _HARD_ASSERTION_EVALUATORS.get(name)
