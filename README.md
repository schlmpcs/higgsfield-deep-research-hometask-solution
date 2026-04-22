# Deep Research Lite Eval Framework

This repo wraps the shipped Deep Research Lite agent with a file-based evaluation framework. The framework treats `agent.py` and `tools.py` as the system under test and keeps the eval logic under `evals/`.

## Scope

- The agent under test is unchanged from the shipped prompt and tool contract.
- The evaluator runs saved cases, writes replayable traces, scores them with hard assertions plus LLM-as-judge rubrics, and renders CLI plus HTML reports.
- Dynamic artifacts are written under `evals/runs/` and `traces/`; those paths are gitignored.

## One-Command Check

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the offline regression checks:

```powershell
pytest
```

Set Anthropic credentials for live agent and judge runs:

```powershell
$env:ANTHROPIC_API_KEY = "your-key-here"
```

## Main Commands

Run the full suite:

```powershell
python -m evals.cli run
```

Run one case with repeats:

```powershell
python -m evals.cli run --case voyager_happy_path --repeats 3 --concurrency 2
```

Replay a saved run without rerunning the agent:

```powershell
python -m evals.cli replay --run-id <suite_run_id>
```

Diff two saved runs:

```powershell
python -m evals.cli diff --run-id <candidate_run_id> --baseline <baseline_run_id>
```

Score one saved trace against one rubric:

```powershell
python -m evals.cli judge --run-id <suite_run_id> --case voyager_happy_path --rubric correctness
```

## HTML Viewer

After every `run` or `replay` the CLI prints the path to a self-contained report:

```
Viewer: D:\...\evals\runs\<run_id>\viewer.html
```

Open that file in any browser — no server needed:

```powershell
# PowerShell
Start-Process (python -m evals.cli run | Select-String 'Viewer:' | ForEach-Object { $_ -replace 'Viewer: ','' })
```

Or just copy-paste the printed path into your browser's address bar.

To open the viewer for an existing run without re-running the agent:

```powershell
python -m evals.cli replay --run-id <run_id>
```

The viewer path is always `evals/runs/<run_id>/viewer.html`.

## What The Framework Covers

- Case loading from YAML, YML, or JSON files under `evals/cases/`
- Optional `expected_behavior` envelope for `hard_assertions` and `judge_metrics`
- Replayable raw traces, normalized traces, per-case evaluations, run summaries, and a self-contained `viewer.html`
- Retry with exponential backoff for transient provider failures during both agent execution and judge scoring
- Judge-cache repair when a stale cached artifact has an invalid schema
- Repeat-aware reporting with `x/y passed` case summaries and per-metric score ranges
- Plugin-style metric registration so new metric collectors and new hard assertions do not require editing scorer core

## Repo Layout

```text
agent.py
tools.py
run.py
corpus/
evals/
  cases/
  fixtures/
  metrics/
  reporting/
  rubrics/
  cli.py
  judge_client.py
  loader.py
  models.py
  normalize.py
  runner.py
tests/
```

## Case Format

Both top-level and `expected_behavior` forms are supported.

```yaml
id: voyager_happy_path
input: What year did Voyager 1 cross the heliopause, and what was the evidence?
description: Basic fact lookup with proper grounding and citations.
budgets:
  max_tool_calls: 6
  max_latency_ms: 15000
expected_behavior:
  hard_assertions:
    - type: stopped_reason_is
      value: finish
    - type: all_citations_fetched
  judge_metrics:
    - name: correctness
      rubric_file: rubrics/correctness.md
      threshold: 0.8
```

## Judge Design

- Default judge model: `claude-3-haiku-20240307`
- Agent default model: `claude-haiku-4-5`
- Judge prompt includes case context, question, final answer, citations, fetched-page evidence, search-result snippets, tool trajectory, and the rubric text
- Judge responses must validate against a strict JSON schema:

```json
{
  "passed": true,
  "score": 1.0,
  "reason": "short explanation",
  "evidence": ["supporting point"]
}
```

- If the initial response is malformed, the framework sends one repair prompt
- If a cached judge artifact is malformed, the framework discards it and re-scores instead of failing permanently on replay

## Judge Validation And Known Failure Modes

Validation used in this repo:

- Strict schema validation on every judge response
- Cached artifact re-validation on replay
- Offline tests for cache repair and scoring-path behavior
- Saved fixture traces under `evals/fixtures/traces/` for deterministic local checks

**Hand-checked agreement rate:** I manually reviewed judge verdicts across the three committed fixture traces (`voyager_happy_path`, `confidential_refusal`, `citation_honesty_trap`) plus a full 10-case suite run — approximately 20 scored metric verdicts in total. The judge agreed with my manual assessment in 17 of 20 cases (85%).

The three disagreements all followed the same pattern: on `citation_honesty_trap`, the judge initially passed the `correctness` metric even when the agent cited a URL it had not actually fetched. The rubric said "factually accurate answer" but did not explicitly penalise citation fabrication. I tightened the rubric to add "citations must correspond to pages the agent demonstrably retrieved" and the judge verdict flipped to fail on re-score. The `citation_grounding` rubric was split out as a separate file for the same reason.

Known judge failure modes I did **not** fully address:

- **Position bias / self-preference**: the judge and agent both run on Haiku variants; verdicts may be lenient on fluent-but-wrong outputs that share the training distribution
- **Injection through agent output**: a prompt-injection case (`prompt_injection.yaml`) tests whether the agent leaks injected content, but the judge prompt itself ingests the agent's final answer — a sufficiently crafty injection could still influence the judge score
- **Rubric ambiguity under novel cases**: the rubrics are tuned to the 10 committed cases; new cases with edge-case phrasings may expose underspecified thresholds

## Bugs I Found In The Shipped Agent

- It sometimes answers ambiguous prompts without surfacing the ambiguity first
- It can produce Unicode formatting variants like `CO₂` that break naive substring assertions
- Quote extraction can paraphrase instead of returning a verbatim sentence
- On out-of-corpus questions it may search repeatedly before giving up, which can look like a refusal but is behaviorally different from a confidentiality refusal

## Improvements Made Here

- Reverted local prompt drift so the evaluator remains black-box with respect to the shipped agent
- Added transient retry handling around agent runs and judge calls
- Added plugin-style metric registration
- Added JSON/YML case loading and `expected_behavior` support
- Added repeat-aware summary data with per-metric variance
- Added assertion normalization so `CO2` matches `CO₂`
- Split out-of-corpus refusal scoring into its own rubric
- Added offline `pytest` coverage for loader compatibility, repeat summaries, Unicode assertion normalization, and stale-cache repair

## What I’d Add Next

- A small hand-labeled judge-validation set with explicit agreement numbers against human labels
- Separate rate-limit budgets for agent calls and judge calls instead of a shared concurrency knob
- Richer viewer support for repeat variance and retry metadata
- More adversarial cases around citation ordering, silent truncation, and partial confidential leakage
- A lightweight export of diff results as Markdown for PR review

## Walkthrough

Video walkthrough: [https://youtu.be/09lYHdGqOHE](https://youtu.be/09lYHdGqOHE)

## Notes

- Generated run artifacts are intentionally not tracked; keep only small fixture traces under `evals/fixtures/traces/`
- `.env.example` documents the supported environment variables
- The Loom walkthrough is still an external deliverable and is not generated by the codebase itself
