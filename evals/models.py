from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class BudgetConfig:
    max_tool_calls: int | None = None
    max_latency_ms: int | None = None


@dataclass(slots=True)
class HardAssertionSpec:
    type: str
    value: Any = None
    match: str | None = None


@dataclass(slots=True)
class JudgeMetricSpec:
    name: str
    rubric_file: str
    threshold: float = 0.8


@dataclass(slots=True)
class TestCase:
    id: str
    input: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    budgets: BudgetConfig = field(default_factory=BudgetConfig)
    hard_assertions: list[HardAssertionSpec] = field(default_factory=list)
    judge_metrics: list[JudgeMetricSpec] = field(default_factory=list)
    source_path: str = ""


@dataclass(slots=True)
class MetricAggregate:
    name: str
    passed_repeats: int
    total_repeats: int
    mean_score: float
    min_score: float
    max_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CaseAggregate:
    case_id: str
    passed_repeats: int
    total_repeats: int
    pass_rate: float
    metric_aggregates: list[MetricAggregate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metric_aggregates"] = [
            metric.to_dict() for metric in self.metric_aggregates
        ]
        return payload


@dataclass(slots=True)
class ToolCallRecord:
    step_index: int
    tool_use_id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    is_error: bool = False
    latency_ms: int = 0


@dataclass(slots=True)
class NormalizedTrace:
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    tool_sequence: list[str] = field(default_factory=list)
    fetched_urls: list[str] = field(default_factory=list)
    cited_urls: list[str] = field(default_factory=list)
    citations_missing_fetch: list[str] = field(default_factory=list)
    final_answer: str | None = None
    stopped_reason: str = ""
    tool_count: int = 0
    search_count: int = 0
    fetch_count: int = 0
    quote_count: int = 0
    finish_count: int = 0
    wall_time_ms: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TraceRecord:
    schema_version: str
    suite_run_id: str
    case_id: str
    repeat_index: int
    timestamp_utc: str
    raw_trace_path: str
    normalized: NormalizedTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_run_id": self.suite_run_id,
            "case_id": self.case_id,
            "repeat_index": self.repeat_index,
            "timestamp_utc": self.timestamp_utc,
            "raw_trace_path": self.raw_trace_path,
            "normalized": self.normalized.to_dict(),
        }


@dataclass(slots=True)
class MetricResult:
    name: str
    kind: Literal["hard", "judge"]
    passed: bool
    score: float
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CaseResult:
    case_id: str
    repeat_index: int
    passed: bool
    metrics: list[MetricResult] = field(default_factory=list)
    trace_path: str = ""
    evaluation_path: str = ""
    wall_time_ms: int = 0
    cost_usd: float = 0.0
    tool_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metrics"] = [metric.to_dict() for metric in self.metrics]
        return payload


@dataclass(slots=True)
class RunSummary:
    suite_run_id: str
    created_at_utc: str
    total_cases: int
    total_executions: int
    passed_executions: int
    pass_rate: float
    total_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    mean_tool_calls: float
    case_summaries: list[CaseAggregate] = field(default_factory=list)
    case_results: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["case_summaries"] = [
            case_summary.to_dict() for case_summary in self.case_summaries
        ]
        payload["case_results"] = [case_result.to_dict() for case_result in self.case_results]
        return payload
