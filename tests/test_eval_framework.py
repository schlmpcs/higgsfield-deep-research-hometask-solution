from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.judge_client import JudgeClient, _hash_request, build_judge_prompt
from evals.loader import load_cases
from evals.metrics.hard_assertions import evaluate_hard_assertion
from evals.models import (
    CaseResult,
    HardAssertionSpec,
    MetricResult,
    NormalizedTrace,
    TraceRecord,
)
from evals.reporting.aggregate import build_run_summary


def test_load_cases_supports_json_and_expected_behavior(tmp_path: Path) -> None:
    case_path = tmp_path / "sample.json"
    case_path.write_text(
        json.dumps(
            {
                "id": "json_case",
                "input": "What is photosynthesis?",
                "expected_behavior": {
                    "hard_assertions": [{"type": "stopped_reason_is", "value": "finish"}],
                    "judge_metrics": [
                        {
                            "name": "correctness",
                            "rubric_file": "rubrics/correctness.md",
                            "threshold": 0.8,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    cases = load_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0].hard_assertions[0].type == "stopped_reason_is"
    assert cases[0].judge_metrics[0].name == "correctness"


def test_run_summary_includes_repeat_and_metric_aggregates() -> None:
    results = [
        CaseResult(
            case_id="voyager_happy_path",
            repeat_index=1,
            passed=True,
            metrics=[
                MetricResult(
                    name="correctness",
                    kind="judge",
                    passed=True,
                    score=1.0,
                    reason="ok",
                )
            ],
        ),
        CaseResult(
            case_id="voyager_happy_path",
            repeat_index=2,
            passed=False,
            metrics=[
                MetricResult(
                    name="correctness",
                    kind="judge",
                    passed=False,
                    score=0.5,
                    reason="partial",
                )
            ],
        ),
    ]

    summary = build_run_summary(suite_run_id="suite", case_results=results)

    assert summary.total_executions == 2
    assert len(summary.case_summaries) == 1
    case_summary = summary.case_summaries[0]
    assert case_summary.passed_repeats == 1
    assert case_summary.total_repeats == 2
    assert case_summary.metric_aggregates[0].name == "correctness"
    assert case_summary.metric_aggregates[0].mean_score == 0.75


def test_answer_contains_normalizes_unicode_subscripts() -> None:
    trace = TraceRecord(
        schema_version="0.1",
        suite_run_id="suite",
        case_id="photosynthesis",
        repeat_index=1,
        timestamp_utc="2026-04-21T00:00:00Z",
        raw_trace_path="trace.json",
        normalized=NormalizedTrace(
            final_answer="Photosynthesis uses CO₂ and H₂O.",
            stopped_reason="finish",
        ),
    )

    metric = evaluate_hard_assertion(
        HardAssertionSpec(type="answer_contains", value="CO2"),
        trace,
    )

    assert metric.passed is True


def test_judge_client_repairs_invalid_cached_artifact(tmp_path: Path) -> None:
    raw_trace = {
        "question": "When did Voyager 1 cross the heliopause?",
        "final_answer": "Voyager 1 crossed in 2012.",
        "citations": ["https://corpus.local/nasa-heliopause-announcement"],
        "messages": [],
    }
    rubric_text = "Return strict JSON."
    prompt = build_judge_prompt(raw_trace, rubric_text, case_id="voyager_happy_path")
    request_hash = _hash_request("claude-3-haiku-20240307", prompt)
    artifact_path = tmp_path / f"{request_hash}.json"
    artifact_path.write_text(
        json.dumps({"model": "claude-3-haiku-20240307", "result": {"score": 1.0}}),
        encoding="utf-8",
    )

    client = JudgeClient(
        model="claude-3-haiku-20240307",
        cache_dir=tmp_path,
        transport=lambda *_args: (
            json.dumps(
                {
                    "passed": True,
                    "score": 1.0,
                    "reason": "ok",
                    "evidence": ["supported"],
                }
            ),
            0.0,
        ),
    )

    artifact = client.score_trace(
        raw_trace=raw_trace,
        trace_path=tmp_path / "trace.json",
        rubric_path=tmp_path / "rubric.md",
        rubric_text=rubric_text,
        case_id="voyager_happy_path",
    )

    assert artifact.cache_hit is False
    repaired = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert repaired["result"]["passed"] is True
