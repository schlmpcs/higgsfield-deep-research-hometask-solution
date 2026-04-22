"""Minimal evaluation framework scaffolding for Deep Research Lite."""

from .loader import DEFAULT_CASES_DIR, CaseLoadError, load_case, load_cases
from .judge_client import (
    JudgeArtifact,
    JudgeClient,
    JudgeScore,
    build_judge_prompt,
    load_rubric,
    load_saved_trace,
    score_saved_trace,
)
from .models import (
    BudgetConfig,
    CaseResult,
    HardAssertionSpec,
    JudgeMetricSpec,
    MetricResult,
    RunSummary,
    TestCase,
)

__all__ = [
    "BudgetConfig",
    "CaseResult",
    "CaseLoadError",
    "DEFAULT_CASES_DIR",
    "HardAssertionSpec",
    "JudgeArtifact",
    "JudgeClient",
    "JudgeMetricSpec",
    "JudgeScore",
    "MetricResult",
    "RunSummary",
    "TestCase",
    "build_judge_prompt",
    "load_case",
    "load_cases",
    "load_rubric",
    "load_saved_trace",
    "score_saved_trace",
]
