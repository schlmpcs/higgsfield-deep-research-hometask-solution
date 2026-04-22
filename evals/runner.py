from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent import run_agent, DEFAULT_MODEL

from .loader import DEFAULT_CASES_DIR, load_cases
from .metrics import evaluate_case
from .models import CaseResult, RunSummary, TestCase, TraceRecord
from .normalize import normalize_trace
from .reporting import build_run_summary, write_case_result, write_run_summary, write_run_viewer

RUNS_DIR = Path(__file__).resolve().parent / "runs"


@dataclass(slots=True)
class RunPlan:
    cases: list[TestCase]
    cases_dir: str
    case_filter: str | None = None
    repeats: int = 1
    concurrency: int = 1


@dataclass(slots=True)
class RunPaths:
    suite_run_id: str
    run_dir: Path
    traces_dir: Path
    normalized_dir: Path
    evaluations_dir: Path
    summary_path: Path
    viewer_path: Path


@dataclass(slots=True)
class ExecutionResult:
    case_id: str
    repeat_index: int
    raw_trace_path: str
    normalized_path: str
    evaluation_path: str
    trace_record: TraceRecord
    case_result: CaseResult


def plan_run(
    *,
    cases_dir: Path = DEFAULT_CASES_DIR,
    case_id: str | None = None,
    repeats: int = 1,
    concurrency: int = 1,
) -> RunPlan:
    cases = load_cases(cases_dir)
    if case_id is not None:
        cases = [case for case in cases if case.id == case_id]
        if not cases:
            raise ValueError(f"unknown case id: {case_id}")

    return RunPlan(
        cases=cases,
        cases_dir=str(cases_dir.resolve()),
        case_filter=case_id,
        repeats=repeats,
        concurrency=concurrency,
    )


def execute_run(run_plan: RunPlan) -> tuple[RunPaths, list[ExecutionResult], RunSummary]:
    run_paths = create_run_paths(run_plan=run_plan)
    executions = [
        (case, repeat_index)
        for case in run_plan.cases
        for repeat_index in range(1, run_plan.repeats + 1)
    ]
    results: list[ExecutionResult] = []

    with ThreadPoolExecutor(max_workers=run_plan.concurrency) as pool:
        futures = {
            pool.submit(execute_case, case, repeat_index, run_paths): (case.id, repeat_index)
            for case, repeat_index in executions
        }
        for future in as_completed(futures):
            results.append(future.result())

    summary = build_run_summary(
        suite_run_id=run_paths.suite_run_id,
        case_results=[result.case_result for result in results],
    )
    write_run_summary(run_paths.summary_path, summary)
    write_run_viewer(run_paths.run_dir)

    return run_paths, results, summary


def replay_run(
    *,
    run_id: str,
    cases_dir: Path = DEFAULT_CASES_DIR,
) -> tuple[Path, list[ExecutionResult], RunSummary]:
    run_dir = RUNS_DIR / run_id
    traces_dir = run_dir / "traces"
    if not traces_dir.exists():
        raise FileNotFoundError(f"trace directory not found: {traces_dir}")

    normalized_dir = run_dir / "normalized"
    evaluations_dir = run_dir / "evaluations"
    judge_cache_dir = run_dir / "judge_cache"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    judge_cache_dir.mkdir(parents=True, exist_ok=True)

    cases = {case.id: case for case in load_cases(cases_dir)}
    results: list[ExecutionResult] = []
    for trace_path in sorted(traces_dir.glob("*.json")):
        case_id, repeat_index = _parse_trace_filename(trace_path.name)
        case = cases.get(case_id)
        if case is None:
            raise ValueError(f"no matching case found for saved trace: {trace_path.name}")
        results.append(
            _evaluate_saved_trace(
                case=case,
                repeat_index=repeat_index,
                run_id=run_id,
                raw_trace_path=trace_path,
                normalized_dir=normalized_dir,
                evaluations_dir=evaluations_dir,
                judge_cache_dir=judge_cache_dir,
            )
        )

    summary = build_run_summary(
        suite_run_id=run_id,
        case_results=[result.case_result for result in results],
    )
    write_run_summary(run_dir / "summary.json", summary)
    write_run_viewer(run_dir)
    return run_dir, results, summary


def create_run_paths(base_dir: Path = RUNS_DIR, run_plan: RunPlan | None = None) -> RunPaths:
    suite_run_id = build_suite_run_id()
    run_dir = base_dir / suite_run_id
    traces_dir = run_dir / "traces"
    normalized_dir = run_dir / "normalized"
    evaluations_dir = run_dir / "evaluations"
    summary_path = run_dir / "summary.json"
    viewer_path = run_dir / "viewer.html"

    traces_dir.mkdir(parents=True, exist_ok=False)
    normalized_dir.mkdir(parents=True, exist_ok=False)
    evaluations_dir.mkdir(parents=True, exist_ok=False)

    config = {
        "suite_run_id": suite_run_id,
        "created_at_utc": utc_now_iso(),
        "cases_dir": run_plan.cases_dir if run_plan else None,
        "repeats": run_plan.repeats if run_plan else None,
        "concurrency": run_plan.concurrency if run_plan else None,
    }
    (run_dir / "run_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )

    return RunPaths(
        suite_run_id=suite_run_id,
        run_dir=run_dir,
        traces_dir=traces_dir,
        normalized_dir=normalized_dir,
        evaluations_dir=evaluations_dir,
        summary_path=summary_path,
        viewer_path=viewer_path,
    )


def execute_case(case: TestCase, repeat_index: int, run_paths: RunPaths) -> ExecutionResult:
    started_at = time.time()
    raw_trace = _run_case_with_retries(case.input, started_at)

    normalized = normalize_trace(raw_trace)

    file_stem = f"{case.id}__r{repeat_index}"
    raw_trace_path = run_paths.traces_dir / f"{file_stem}.json"
    normalized_path = run_paths.normalized_dir / f"{file_stem}.json"
    evaluation_path = run_paths.evaluations_dir / f"{file_stem}.json"

    _write_json(raw_trace_path, raw_trace)

    return _evaluate_trace_payload(
        case=case,
        repeat_index=repeat_index,
        run_id=run_paths.suite_run_id,
        raw_trace=raw_trace,
        raw_trace_path=raw_trace_path,
        normalized_path=normalized_path,
        evaluation_path=evaluation_path,
        judge_cache_dir=run_paths.run_dir / "judge_cache",
        normalized=normalized,
    )


def build_suite_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


def utc_now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _build_error_trace(question: str, exc: Exception, started_at: float) -> dict[str, object]:
    wall_time_ms = int((time.time() - started_at) * 1000)
    return {
        "run_id": f"error-{uuid4()}",
        "question": question,
        "model": os.getenv("DRL_MODEL", DEFAULT_MODEL),
        "messages": [
            {"role": "system", "content": ""},
            {"role": "user", "content": question},
        ],
        "final_answer": None,
        "citations": [],
        "stopped_reason": "error",
        "total_tokens": {"input": 0, "output": 0},
        "cost_usd": 0.0,
        "wall_time_ms": wall_time_ms,
        "error": f"{type(exc).__name__}: {exc}",
    }


def _run_case_with_retries(
    question: str,
    started_at: float,
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
) -> dict[str, object]:
    transient_errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            result = run_agent(question)
            raw_trace = result.to_dict()
        except Exception as exc:
            if attempt >= max_attempts or not _is_transient_error(exc):
                raw_trace = _build_error_trace(question, exc, started_at)
                break
            transient_errors.append(f"{type(exc).__name__}: {exc}")
            _sleep_for_retry(attempt, base_delay_s)
            continue

        error_text = str(raw_trace.get("error") or "")
        if (
            raw_trace.get("stopped_reason") == "error"
            and error_text
            and attempt < max_attempts
            and _is_transient_error_message(error_text)
        ):
            transient_errors.append(error_text)
            _sleep_for_retry(attempt, base_delay_s)
            continue
        break

    if transient_errors:
        raw_trace["eval_retry"] = {
            "attempt_count": len(transient_errors) + 1,
            "transient_errors": transient_errors,
        }
    raw_trace["wall_time_ms"] = int((time.time() - started_at) * 1000)
    return raw_trace


def _evaluate_saved_trace(
    *,
    case: TestCase,
    repeat_index: int,
    run_id: str,
    raw_trace_path: Path,
    normalized_dir: Path,
    evaluations_dir: Path,
    judge_cache_dir: Path,
) -> ExecutionResult:
    raw_trace = json.loads(raw_trace_path.read_text(encoding="utf-8"))
    file_stem = raw_trace_path.stem
    return _evaluate_trace_payload(
        case=case,
        repeat_index=repeat_index,
        run_id=run_id,
        raw_trace=raw_trace,
        raw_trace_path=raw_trace_path,
        normalized_path=normalized_dir / f"{file_stem}.json",
        evaluation_path=evaluations_dir / f"{file_stem}.json",
        judge_cache_dir=judge_cache_dir,
    )


def _evaluate_trace_payload(
    *,
    case: TestCase,
    repeat_index: int,
    run_id: str,
    raw_trace: dict[str, object],
    raw_trace_path: Path,
    normalized_path: Path,
    evaluation_path: Path,
    judge_cache_dir: Path,
    normalized=None,
) -> ExecutionResult:
    normalized = normalized or normalize_trace(raw_trace)
    trace_record = TraceRecord(
        schema_version="0.1",
        suite_run_id=run_id,
        case_id=case.id,
        repeat_index=repeat_index,
        timestamp_utc=utc_now_iso(),
        raw_trace_path=str(raw_trace_path.resolve()),
        normalized=normalized,
    )
    _write_json(normalized_path, trace_record.to_dict())
    case_result = evaluate_case(
        case=case,
        trace=trace_record,
        raw_trace=raw_trace,
        raw_trace_path=raw_trace_path,
        evaluation_path=evaluation_path,
        judge_cache_dir=judge_cache_dir,
    )
    write_case_result(evaluation_path, case_result)
    return ExecutionResult(
        case_id=case.id,
        repeat_index=repeat_index,
        raw_trace_path=str(raw_trace_path.resolve()),
        normalized_path=str(normalized_path.resolve()),
        evaluation_path=str(evaluation_path.resolve()),
        trace_record=trace_record,
        case_result=case_result,
    )


def _parse_trace_filename(filename: str) -> tuple[str, int]:
    match = re.match(r"^(?P<case_id>.+)__r(?P<repeat>\d+)\.json$", filename)
    if match is None:
        raise ValueError(f"trace filename does not match <case_id>__rN.json: {filename}")
    return match.group("case_id"), int(match.group("repeat"))


def _sleep_for_retry(attempt: int, base_delay_s: float) -> None:
    delay = base_delay_s * (2 ** (attempt - 1)) + random.uniform(0.0, 0.25)
    time.sleep(delay)


def _is_transient_error(exc: Exception) -> bool:
    return _is_transient_error_message(f"{type(exc).__name__}: {exc}")


def _is_transient_error_message(message: str) -> bool:
    normalized = message.lower()
    transient_markers = [
        "429",
        "500",
        "502",
        "503",
        "504",
        "rate limit",
        "overloaded",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "connection refused",
        "apiconnectionerror",
        "apitimeouterror",
        "internalservererror",
        "ratelimiterror",
    ]
    return any(marker in normalized for marker in transient_markers)
