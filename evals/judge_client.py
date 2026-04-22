from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from anthropic import Anthropic

from .models import NormalizedTrace
from .normalize import normalize_trace

RUBRICS_DIR = Path(__file__).resolve().parent / "rubrics"
RUNS_DIR = Path(__file__).resolve().parent / "runs"
DEFAULT_JUDGE_MODEL = os.getenv("DRL_JUDGE_MODEL", "claude-haiku-4-5-20251001")
JUDGE_SYSTEM_PROMPT = """You are grading one evaluation case for a research agent.
Follow the rubric exactly.
Return JSON only.
"""


@dataclass(slots=True)
class JudgeScore:
    passed: bool
    score: float
    reason: str
    evidence: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class JudgeArtifact:
    model: str
    request_hash: str
    trace_path: str
    rubric_path: str
    artifact_path: str
    cache_hit: bool
    score: JudgeScore
    cost_usd: float = 0.0


def load_rubric(rubric_file: str | Path) -> tuple[Path, str]:
    rubric_path = _resolve_rubric_path(rubric_file)
    try:
        rubric_text = rubric_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"could not read rubric file {rubric_path}: {exc}") from exc
    return rubric_path, rubric_text


def load_saved_trace(run_id: str, case_id: str, repeat_index: int = 1) -> tuple[Path, dict[str, Any]]:
    trace_path = RUNS_DIR / run_id / "traces" / f"{case_id}__r{repeat_index}.json"
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"saved trace not found: {trace_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in saved trace {trace_path}: {exc}") from exc
    return trace_path, payload


def build_judge_prompt(
    raw_trace: dict[str, Any],
    rubric_text: str,
    *,
    case_id: str | None = None,
    case_description: str | None = None,
    metric_name: str | None = None,
) -> str:
    normalized = normalize_trace(raw_trace)
    citations = normalized.cited_urls or []
    trajectory = _build_trajectory_from_normalized(normalized)
    evidence_block = _build_evidence_block(normalized, char_limit=3000)
    search_results_block = _build_search_results_block(normalized, char_limit=1800)
    question = _trim_text(str(raw_trace.get("question", "")), 800)
    final_answer = _trim_text(str(raw_trace.get("final_answer") or ""), 1500)
    rubric = _trim_text(rubric_text, 4000)
    citations_block = _trim_text(json.dumps(citations, indent=2), 1200)
    case_context = _trim_text(
        "\n".join(
            part
            for part in [
                f"case_id={case_id}" if case_id else "",
                f"metric_name={metric_name}" if metric_name else "",
                case_description or "",
            ]
            if part
        ),
        800,
    )

    return "\n".join(
        [
            "<CaseContext>",
            case_context or "No additional case context provided.",
            "</CaseContext>",
            "<Question>",
            question,
            "</Question>",
            "<FinalAnswer>",
            final_answer,
            "</FinalAnswer>",
            "<Citations>",
            citations_block,
            "</Citations>",
            "<Evidence>",
            evidence_block,
            "</Evidence>",
            "<SearchResults>",
            search_results_block,
            "</SearchResults>",
            "<Trajectory>",
            trajectory,
            "</Trajectory>",
            "<Rubric>",
            rubric,
            "</Rubric>",
        ]
    )


def score_saved_trace(
    *,
    run_id: str,
    case_id: str,
    rubric_file: str | Path,
    repeat_index: int = 1,
    model: str | None = None,
    transport: Callable[[str, str, str, int], tuple[str, float]] | None = None,
) -> JudgeArtifact:
    trace_path, raw_trace = load_saved_trace(run_id, case_id, repeat_index)
    run_dir = RUNS_DIR / run_id
    rubric_path, rubric_text = load_rubric(rubric_file)
    client = JudgeClient(
        model=model or DEFAULT_JUDGE_MODEL,
        cache_dir=run_dir / "judge_cache",
        transport=transport,
    )
    return client.score_trace(
        raw_trace=raw_trace,
        trace_path=trace_path,
        rubric_path=rubric_path,
        rubric_text=rubric_text,
        case_id=case_id,
        metric_name=Path(rubric_file).stem,
    )


class JudgeClient:
    def __init__(
        self,
        *,
        model: str = DEFAULT_JUDGE_MODEL,
        cache_dir: Path | None = None,
        transport: Callable[[str, str, str, int], tuple[str, float]] | None = None,
    ) -> None:
        self.model = model
        self.cache_dir = cache_dir or (RUNS_DIR / "judge_cache")
        self.transport = transport or _anthropic_transport

    def score_trace(
        self,
        *,
        raw_trace: dict[str, Any],
        trace_path: Path,
        rubric_path: Path,
        rubric_text: str,
        case_id: str | None = None,
        case_description: str | None = None,
        metric_name: str | None = None,
    ) -> JudgeArtifact:
        prompt = build_judge_prompt(
            raw_trace,
            rubric_text,
            case_id=case_id,
            case_description=case_description,
            metric_name=metric_name,
        )
        request_hash = _hash_request(self.model, prompt)
        artifact_path = self.cache_dir / f"{request_hash}.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if artifact_path.exists():
            try:
                cached = json.loads(artifact_path.read_text(encoding="utf-8"))
                score = _validate_judge_payload(cached.get("result"))
            except (OSError, json.JSONDecodeError, ValueError):
                artifact_path.unlink(missing_ok=True)
            else:
                return JudgeArtifact(
                    model=str(cached.get("model", self.model)),
                    request_hash=request_hash,
                    trace_path=str(trace_path.resolve()),
                    rubric_path=str(rubric_path.resolve()),
                    artifact_path=str(artifact_path.resolve()),
                    cache_hit=True,
                    score=score,
                )

        attempts: list[dict[str, Any]] = []
        total_cost_usd = 0.0
        raw_response, call_cost = _call_with_retries(
            lambda: self.transport(self.model, JUDGE_SYSTEM_PROMPT, prompt, 1024)
        )
        total_cost_usd += call_cost
        attempts.append({"kind": "initial", "raw_response": raw_response})

        try:
            score = _parse_judge_response(raw_response)
        except ValueError as exc:
            repair_prompt = _build_repair_prompt(raw_response, str(exc))
            repaired_response, repair_cost = _call_with_retries(
                lambda: self.transport(
                    self.model,
                    JUDGE_SYSTEM_PROMPT,
                    repair_prompt,
                    512,
                )
            )
            total_cost_usd += repair_cost
            attempts.append({"kind": "repair", "raw_response": repaired_response})
            score = _parse_judge_response(repaired_response)

        artifact_payload = {
            "model": self.model,
            "request_hash": request_hash,
            "trace_path": str(trace_path.resolve()),
            "rubric_path": str(rubric_path.resolve()),
            "prompt": prompt,
            "attempts": attempts,
            "result": score.to_dict(),
        }
        artifact_path.write_text(
            json.dumps(artifact_payload, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        return JudgeArtifact(
            model=self.model,
            request_hash=request_hash,
            trace_path=str(trace_path.resolve()),
            rubric_path=str(rubric_path.resolve()),
            artifact_path=str(artifact_path.resolve()),
            cache_hit=False,
            score=score,
            cost_usd=total_cost_usd,
        )


_PRICE_PER_1M: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}


def _price(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _PRICE_PER_1M.get(model, (3.00, 15.00))
    return (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000


def _anthropic_transport(model: str, system: str, prompt: str, max_tokens: int) -> tuple[str, float]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Judge scoring requires API access.")

    client = Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    cost = _price(model, response.usage.input_tokens, response.usage.output_tokens)
    return text, cost


def _resolve_rubric_path(rubric_file: str | Path) -> Path:
    candidate = Path(rubric_file)
    if not candidate.suffix:
        candidate = candidate.with_suffix(".md")

    if candidate.is_absolute():
        return candidate

    parts = candidate.parts
    if parts and parts[0] == "rubrics":
        candidate = Path(*parts[1:])

    return (RUBRICS_DIR / candidate).resolve()


def _hash_request(model: str, prompt: str) -> str:
    digest = hashlib.sha256()
    digest.update(model.encode("utf-8"))
    digest.update(b"\n")
    digest.update(prompt.encode("utf-8"))
    return digest.hexdigest()


def _build_evidence_block(normalized: NormalizedTrace, char_limit: int) -> str:
    snippets: list[str] = []
    for call in normalized.tool_calls:
        if call.name != "fetch_url" or call.is_error:
            continue
        url = call.args.get("url", "")
        text = str(call.output or "")[:1000]
        snippets.append(f"[{url}]\n{text}")
    block = "\n\n".join(snippets)
    return _trim_text(block, char_limit) if block else "No fetched page text available."


def _build_search_results_block(normalized: NormalizedTrace, char_limit: int) -> str:
    snippets: list[str] = []
    for call in normalized.tool_calls:
        if call.name != "web_search" or call.is_error or not isinstance(call.output, list):
            continue
        for result in call.output[:3]:
            if not isinstance(result, dict):
                continue
            url = result.get("url", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            snippets.append(f"[{url}] {title}\n{snippet}")
    block = "\n\n".join(snippets)
    return _trim_text(block, char_limit) if block else "No search results available."


def _build_trajectory_from_normalized(normalized: NormalizedTrace) -> str:
    if not normalized.tool_calls:
        return "No tool calls were recorded."

    lines: list[str] = []
    for index, call in enumerate(normalized.tool_calls[:12], start=1):
        args_summary = _summarize_tool_args(call.name, call.args)
        status = "error" if call.is_error else "ok"
        lines.append(f"{index}. {call.name}({args_summary}) [{status}]")

    if len(normalized.tool_calls) > 12:
        omitted = len(normalized.tool_calls) - 12
        lines.append(f"... {omitted} additional tool call(s) omitted.")

    return _trim_text("\n".join(lines), 1800)


def _summarize_tool_args(name: str, args: dict[str, Any]) -> str:
    if name == "web_search":
        return f"query={_repr_trim(args.get('query', ''))}"
    if name == "fetch_url":
        return f"url={_repr_trim(args.get('url', ''))}"
    if name == "extract_quotes":
        return f"topic={_repr_trim(args.get('topic', ''))}"
    if name == "finish":
        citations = args.get("citations", [])
        citations_count = len(citations) if isinstance(citations, list) else 0
        return f"citations={citations_count}"
    return _repr_trim(json.dumps(args, ensure_ascii=True))


def _repr_trim(value: Any, limit: int = 120) -> str:
    return repr(_trim_text(str(value), limit))


def _build_repair_prompt(raw_response: str, error: str) -> str:
    return "\n".join(
        [
            "Your previous response was invalid.",
            f"Validation error: {error}",
            'Rewrite it as strict JSON with exactly these fields: {"passed": bool, "score": float, "reason": str, "evidence": list[str]}',
            "Return JSON only.",
            "<InvalidResponse>",
            _trim_text(raw_response, 3000),
            "</InvalidResponse>",
        ]
    )


def _parse_judge_response(raw_response: str) -> JudgeScore:
    cleaned = _clean_json_text(raw_response)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {exc}") from exc
    return _validate_judge_payload(payload)


def _clean_json_text(raw_response: str) -> str:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start : end + 1]
    return cleaned.strip()


def _validate_judge_payload(payload: Any) -> JudgeScore:
    if not isinstance(payload, dict):
        raise ValueError("judge payload must be a JSON object")

    required_keys = {"passed", "score", "reason", "evidence"}
    missing_keys = sorted(required_keys - set(payload))
    if missing_keys:
        raise ValueError(f"missing required field(s): {missing_keys}")

    passed = payload["passed"]
    if not isinstance(passed, bool):
        raise ValueError("'passed' must be a boolean")

    score_raw = payload["score"]
    if not isinstance(score_raw, (int, float)) or isinstance(score_raw, bool):
        raise ValueError("'score' must be numeric")
    score = float(score_raw)
    if score < 0.0 or score > 1.0:
        raise ValueError("'score' must be between 0.0 and 1.0")

    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("'reason' must be a non-empty string")

    evidence_raw = payload["evidence"]
    if not isinstance(evidence_raw, list):
        raise ValueError("'evidence' must be a list of strings")
    evidence: list[str] = []
    for item in evidence_raw:
        if not isinstance(item, str):
            raise ValueError("'evidence' entries must be strings")
        evidence.append(item)

    return JudgeScore(
        passed=passed,
        score=score,
        reason=reason.strip(),
        evidence=evidence,
    )


def _trim_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _call_with_retries(
    func: Callable[[], tuple[str, float]],
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
) -> tuple[str, float]:
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:
            if attempt >= max_attempts or not _is_transient_error(exc):
                raise
            delay = base_delay_s * (2 ** (attempt - 1)) + random.uniform(0.0, 0.25)
            time.sleep(delay)


def _is_transient_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
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
    return any(marker in message for marker in transient_markers)
