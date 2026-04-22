from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .aggregate import load_case_results, load_run_summary


def write_run_viewer(run_dir: Path) -> Path:
    payload = build_viewer_payload(run_dir)
    html = render_run_viewer_html(payload)
    viewer_path = run_dir / "viewer.html"
    viewer_path.write_text(html, encoding="utf-8")
    return viewer_path


def build_viewer_payload(run_dir: Path) -> dict[str, Any]:
    summary = load_run_summary(run_dir)
    evaluation_payloads = load_case_results(run_dir)
    evaluation_index = {
        _execution_key(
            str(item.get("case_id", "")),
            int(item.get("repeat_index", 0)),
        ): item
        for item in evaluation_payloads
    }

    case_groups: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case_result in summary.get("case_results", []):
        case_id = str(case_result.get("case_id", ""))
        grouped.setdefault(case_id, []).append(case_result)

    for case_id, repeats in grouped.items():
        executions: list[dict[str, Any]] = []
        for repeat_summary in sorted(repeats, key=lambda item: int(item.get("repeat_index", 0))):
            repeat_index = int(repeat_summary.get("repeat_index", 0))
            key = _execution_key(case_id, repeat_index)
            evaluation = evaluation_index.get(key, repeat_summary)
            trace_path = _resolve_artifact_path(
                run_dir,
                evaluation.get("trace_path"),
                run_dir / "traces" / f"{case_id}__r{repeat_index}.json",
            )
            normalized_path = run_dir / "normalized" / f"{case_id}__r{repeat_index}.json"
            raw_trace = _read_json(trace_path)
            normalized_payload = _read_json(normalized_path) if normalized_path.exists() else {}
            normalized = (
                normalized_payload.get("normalized", {})
                if isinstance(normalized_payload, dict)
                else {}
            )
            metrics = evaluation.get("metrics", [])
            failed_metrics = [metric for metric in metrics if not metric.get("passed")]

            messages = raw_trace.get("messages", [])
            executions.append(
                {
                    "case_id": case_id,
                    "repeat_index": repeat_index,
                    "passed": bool(evaluation.get("passed", False)),
                    "metrics": metrics,
                    "failed_metrics": failed_metrics,
                    "question": raw_trace.get("question", ""),
                    "final_answer": raw_trace.get("final_answer"),
                    "citations": raw_trace.get("citations", []),
                    "messages": messages,
                    "message_count": len(messages),
                    "stopped_reason": raw_trace.get("stopped_reason", ""),
                    "error": raw_trace.get("error"),
                    "model": raw_trace.get("model", ""),
                    "run_id": raw_trace.get("run_id", ""),
                    "total_tokens": raw_trace.get("total_tokens", {}),
                    "wall_time_ms": int(evaluation.get("wall_time_ms", 0)),
                    "cost_usd": float(evaluation.get("cost_usd", 0.0)),
                    "tool_count": int(evaluation.get("tool_count", 0)),
                    "normalized": normalized,
                    "artifacts": {
                        "trace_path": _relative_artifact_path(run_dir, trace_path.resolve()),
                        "evaluation_path": _relative_artifact_path(
                            run_dir,
                            _resolve_artifact_path(
                                run_dir,
                                evaluation.get("evaluation_path"),
                                run_dir / "evaluations" / f"{case_id}__r{repeat_index}.json",
                            ).resolve(),
                        ),
                        "normalized_path": _relative_artifact_path(run_dir, normalized_path.resolve()),
                    },
                }
            )

        pass_count = sum(1 for execution in executions if execution["passed"])
        case_groups.append(
            {
                "case_id": case_id,
                "overall_passed": pass_count == len(executions),
                "pass_count": pass_count,
                "repeat_count": len(executions),
                "executions": executions,
            }
        )

    case_groups.sort(key=lambda item: (item["overall_passed"], item["case_id"]))
    return {
        "suite_run_id": summary.get("suite_run_id", run_dir.name),
        "generated_at_utc": _utc_now_iso(),
        "summary": summary,
        "cases": case_groups,
    }


def render_run_viewer_html(payload: dict[str, Any]) -> str:
    run_data_json = json.dumps(payload, ensure_ascii=True).replace("</script>", "<\\/script>")
    template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deep Research Lite Eval Viewer</title>
<style>
:root {
  color-scheme: dark;
  --bg: #121416;
  --bg-2: #0c0e10;
  --surface: #1a1c1e;
  --surface-2: #1e2022;
  --surface-3: #282a2c;
  --surface-4: #333537;
  --line: #404752;
  --line-soft: rgba(64, 71, 82, 0.45);
  --text: #e2e2e5;
  --muted: #8a919e;
  --muted-2: #c0c7d5;
  --primary: #a2c9ff;
  --primary-strong: #2694f6;
  --success: #dfed00;
  --success-ink: #1b1d00;
  --danger: #ffb4ab;
  --danger-strong: #93000a;
  --shadow: 0 28px 80px rgba(0, 0, 0, 0.35);
  --radius-xl: 28px;
  --radius-lg: 20px;
  --radius-md: 14px;
  --mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
  --headline: Bahnschrift, "Arial Narrow", "Segoe UI", sans-serif;
  --body: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  --label: "Segoe UI Semibold", "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: var(--body);
  color: var(--text);
  background:
    radial-gradient(circle at top right, rgba(38, 148, 246, 0.15), transparent 26%),
    radial-gradient(circle at 18% 16%, rgba(223, 237, 0, 0.08), transparent 18%),
    linear-gradient(180deg, var(--bg-2) 0%, var(--bg) 14%, #101214 100%);
}
a { color: inherit; }
button, input, select { font: inherit; }
button { cursor: pointer; }
.app {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  min-height: 100vh;
}
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background:
    linear-gradient(180deg, rgba(30, 32, 34, 0.96), rgba(18, 20, 22, 0.98)),
    var(--surface-2);
  border-right: 1px solid var(--line-soft);
  box-shadow: 1px 0 0 rgba(64, 71, 82, 0.2);
  z-index: 20;
}
.rail-header {
  padding: 28px 24px 18px;
  border-bottom: 1px solid var(--line-soft);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), transparent);
}
.brand {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.brand-mark {
  font-family: var(--headline);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.06em;
  color: #fff;
}
.eyebrow {
  font-family: var(--label);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--muted);
}
.rail-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 18px;
}
.mini-stat {
  padding: 12px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(12, 14, 16, 0.72);
}
.mini-stat .label,
.kpi .label,
.detail-label,
.subtle {
  font-family: var(--label);
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--muted);
}
.mini-stat .value {
  margin-top: 6px;
  font-family: var(--headline);
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}
.search-wrap {
  position: relative;
  margin-top: 18px;
}
.search-input {
  width: 100%;
  padding: 14px 14px 14px 42px;
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: rgba(12, 14, 16, 0.86);
  color: var(--text);
  outline: none;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}
.search-input:focus {
  border-color: rgba(162, 201, 255, 0.5);
  box-shadow: 0 0 0 3px rgba(162, 201, 255, 0.08);
}
.search-icon {
  position: absolute;
  top: 50%;
  left: 14px;
  transform: translateY(-50%);
  color: var(--muted);
  font-size: 13px;
}
.case-rail {
  flex: 1;
  overflow: auto;
  padding: 14px 12px 18px;
}
.case-rail::-webkit-scrollbar,
.main-scroll::-webkit-scrollbar {
  width: 8px;
}
.case-rail::-webkit-scrollbar-thumb,
.main-scroll::-webkit-scrollbar-thumb {
  background: rgba(64, 71, 82, 0.8);
  border-radius: 999px;
}
.case-section {
  margin-bottom: 20px;
}
.section-title {
  padding: 10px 12px;
  font-family: var(--label);
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--muted);
}
.section-title.fail {
  color: var(--danger);
}
.section-title.pass {
  color: var(--success);
}
.case-list {
  display: grid;
  gap: 10px;
}
.case-item {
  width: 100%;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-left: 3px solid transparent;
  border-radius: 18px;
  text-align: left;
  color: var(--text);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.01)),
    rgba(30, 32, 34, 0.76);
  transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
}
.case-item:hover {
  transform: translateY(-1px);
  border-color: rgba(162, 201, 255, 0.18);
}
.case-item.active {
  border-color: rgba(223, 237, 0, 0.12);
  border-left-color: var(--success);
  background:
    linear-gradient(180deg, rgba(56, 57, 60, 0.72), rgba(30, 32, 34, 0.94)),
    rgba(30, 32, 34, 0.95);
  box-shadow: inset 0 0 0 1px rgba(223, 237, 0, 0.12);
}
.case-item.pass.active {
  border-left-color: var(--primary);
  box-shadow: inset 0 0 0 1px rgba(162, 201, 255, 0.12);
}
.case-item.empty-state {
  cursor: default;
  color: var(--muted);
}
.case-title {
  margin: 0 0 8px;
  font-family: var(--headline);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.03em;
  word-break: break-word;
}
.case-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: var(--muted-2);
  font-size: 12px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 6px 11px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-family: var(--label);
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  white-space: nowrap;
}
.chip::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0 0 12px currentColor;
}
.chip.pass {
  color: var(--success);
  background: rgba(223, 237, 0, 0.12);
  border-color: rgba(223, 237, 0, 0.18);
}
.chip.fail {
  color: var(--danger);
  background: rgba(255, 180, 171, 0.1);
  border-color: rgba(255, 180, 171, 0.18);
}
.chip.neutral {
  color: var(--primary);
  background: rgba(162, 201, 255, 0.12);
  border-color: rgba(162, 201, 255, 0.18);
}
.chip.system {
  color: var(--muted-2);
  background: rgba(138, 145, 158, 0.12);
  border-color: rgba(138, 145, 158, 0.18);
}
.chip.warn {
  color: #ffd79d;
  background: rgba(255, 215, 157, 0.12);
  border-color: rgba(255, 215, 157, 0.16);
}
.main {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.command-bar {
  position: sticky;
  top: 0;
  z-index: 15;
  padding: 18px 28px;
  border-bottom: 1px solid var(--line-soft);
  background:
    linear-gradient(180deg, rgba(30, 32, 34, 0.92), rgba(12, 14, 16, 0.82)),
    rgba(12, 14, 16, 0.86);
  backdrop-filter: blur(18px);
}
.command-inner {
  display: flex;
  gap: 18px;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
}
.command-title {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.command-title h1 {
  margin: 0;
  font-family: var(--headline);
  font-size: 34px;
  line-height: 0.94;
  letter-spacing: -0.08em;
  color: #fff;
}
.command-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--muted-2);
  font-size: 12px;
}
.command-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(110px, 1fr));
  gap: 10px;
}
.kpi {
  min-width: 110px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(18, 20, 22, 0.84);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.kpi .value {
  display: block;
  margin-top: 6px;
  font-family: var(--headline);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.04em;
  color: #fff;
}
.kpi.emphasis .value {
  color: var(--success);
}
.kpi.alert .value {
  color: var(--danger);
}
.main-scroll {
  flex: 1;
  overflow: auto;
}
.content {
  max-width: 1480px;
  margin: 0 auto;
  padding: 26px 28px 44px;
}
.hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 22px;
  padding: 28px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-top: 2px solid rgba(223, 237, 0, 0.5);
  border-radius: var(--radius-xl);
  background:
    radial-gradient(circle at top right, rgba(147, 0, 10, 0.18), transparent 30%),
    radial-gradient(circle at bottom left, rgba(38, 148, 246, 0.14), transparent 26%),
    linear-gradient(180deg, rgba(30, 32, 34, 0.92), rgba(18, 20, 22, 0.98));
  box-shadow: var(--shadow);
}
.hero.pass {
  border-top-color: rgba(162, 201, 255, 0.6);
}
.hero-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.9fr);
  gap: 24px;
  align-items: start;
}
.hero-title {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 18px;
}
.hero h2 {
  margin: 0;
  font-family: var(--headline);
  font-size: clamp(34px, 5vw, 58px);
  line-height: 0.96;
  letter-spacing: -0.08em;
  color: #fff;
}
.hero p {
  margin: 0;
  color: var(--muted-2);
  line-height: 1.65;
}
.prompt-block {
  margin-top: 18px;
  max-width: 860px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.metric-card {
  padding: 16px;
  border-radius: 18px;
  background: rgba(12, 14, 16, 0.74);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.metric-card .value {
  margin-top: 6px;
  font-family: var(--headline);
  font-size: 30px;
  line-height: 1;
  letter-spacing: -0.06em;
  color: #fff;
}
.metric-card .value.fail {
  color: var(--danger);
}
.metric-card .value.pass {
  color: var(--success);
}
.hero-footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 18px;
  margin-top: 24px;
  align-items: end;
}
.failure-strip {
  min-height: 88px;
  padding: 16px 18px;
  border-radius: 18px;
  border: 1px solid rgba(255, 180, 171, 0.15);
  background: rgba(147, 0, 10, 0.13);
}
.failure-strip.pass {
  border-color: rgba(223, 237, 0, 0.12);
  background: rgba(223, 237, 0, 0.08);
}
.failure-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}
.failure-item {
  padding-left: 14px;
  position: relative;
  color: var(--muted-2);
  line-height: 1.5;
}
.failure-item::before {
  content: "";
  position: absolute;
  top: 0.7em;
  left: 0;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--danger);
  box-shadow: 0 0 10px rgba(255, 180, 171, 0.55);
}
.timeline-meter {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(12, 14, 16, 0.7);
}
.meter-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 10px;
  font-family: var(--label);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
}
.meter-bar {
  position: relative;
  height: 9px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(64, 71, 82, 0.5);
}
.meter-fill {
  position: absolute;
  inset: 0 auto 0 0;
  width: 100%;
  background: linear-gradient(90deg, rgba(38, 148, 246, 0.78), rgba(223, 237, 0, 0.88));
}
.meter-fill.fail {
  background: linear-gradient(90deg, rgba(38, 148, 246, 0.72), rgba(147, 0, 10, 0.96));
}
.meter-marker {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  border-radius: 999px;
  border: 2px solid rgba(12, 14, 16, 0.9);
  background: var(--success);
  box-shadow: 0 0 20px rgba(223, 237, 0, 0.5);
  transform: translate(-50%, -50%);
}
.meter-marker.fail {
  background: var(--danger);
  box-shadow: 0 0 20px rgba(255, 180, 171, 0.42);
}
.panel-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 22px;
  align-items: start;
}
.panel-stack {
  display: grid;
  gap: 22px;
  min-width: 0;
  align-content: start;
}
.panel,
.evidence-card,
.timeline-card,
.message-card {
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-lg);
  background:
    linear-gradient(180deg, rgba(30, 32, 34, 0.82), rgba(18, 20, 22, 0.95)),
    var(--surface);
  box-shadow: var(--shadow);
}
.panel,
.timeline-card {
  padding: 22px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 16px;
}
.panel-header h3,
.timeline-card h3 {
  margin: 0;
  font-family: var(--headline);
  font-size: 24px;
  letter-spacing: -0.04em;
  color: #fff;
}
.answer-text,
.prompt-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.prompt-text {
  font-size: clamp(18px, 2vw, 24px);
  line-height: 1.55;
  color: #fff;
}
.answer-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--muted-2);
}
.error-box {
  margin-top: 18px;
  padding: 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 180, 171, 0.18);
  background: rgba(147, 0, 10, 0.12);
}
.evidence-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 22px;
}
.evidence-card {
  overflow: hidden;
  min-width: 0;
}
.evidence-card .card-inner {
  padding: 20px;
}
.evidence-card.accent {
  border-top: 2px solid rgba(223, 237, 0, 0.55);
}
.evidence-card.primary {
  border-top: 2px solid rgba(162, 201, 255, 0.55);
}
.evidence-card.alert {
  border-top: 2px solid rgba(255, 180, 171, 0.55);
}
.citation-list,
.artifact-list,
.metrics-list,
.timeline-list,
.summary-grid,
.trace-grid {
  display: grid;
  gap: 12px;
}
.citation-item,
.artifact-item,
.metric-item,
.trace-item {
  padding: 14px 15px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  background: rgba(12, 14, 16, 0.56);
}
.citation-link {
  color: var(--primary);
  text-decoration: none;
  word-break: break-all;
}
.citation-link:hover {
  text-decoration: underline;
}
.artifact-item code,
pre {
  font-family: var(--mono);
}
.artifact-item code {
  display: block;
  margin-top: 8px;
  color: var(--muted-2);
  word-break: break-all;
}
.metrics-list {
  gap: 14px;
}
.metric-item.fail {
  border-color: rgba(255, 180, 171, 0.18);
  background: rgba(147, 0, 10, 0.12);
}
.metric-item.pass {
  border-color: rgba(223, 237, 0, 0.14);
  background: rgba(223, 237, 0, 0.08);
}
.metric-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}
.metric-name {
  margin: 0;
  font-weight: 700;
  color: #fff;
}
.metric-bar {
  position: relative;
  height: 6px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(64, 71, 82, 0.46);
}
.metric-bar > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(162, 201, 255, 0.9), rgba(223, 237, 0, 0.95));
}
.metric-item.fail .metric-bar > span {
  background: linear-gradient(90deg, rgba(255, 180, 171, 0.9), rgba(147, 0, 10, 0.95));
}
.metric-reason {
  margin: 0;
  color: var(--muted-2);
  line-height: 1.55;
}
.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  color: var(--muted);
  font-size: 11px;
  font-family: var(--label);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.drawer,
.tool-drawer {
  min-width: 0;
  max-width: 100%;
  margin-top: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  background: rgba(12, 14, 16, 0.56);
}
details > summary {
  list-style: none;
}
details > summary::-webkit-details-marker {
  display: none;
}
.drawer summary,
.tool-drawer summary {
  min-width: 0;
  max-width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 13px 15px;
  cursor: pointer;
  font-family: var(--label);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted-2);
  overflow-wrap: anywhere;
  word-break: break-word;
}
.drawer summary::after,
.tool-drawer summary::after {
  content: "+";
  color: var(--primary);
  font-size: 16px;
  line-height: 1;
}
details[open] > summary::after {
  content: "-";
}
pre {
  margin: 0;
  padding: 16px;
  max-width: 100%;
  min-width: 0;
  overflow: auto;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  color: #d8e4f5;
  background: rgba(5, 7, 8, 0.75);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.trace-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.trace-item .value {
  margin-top: 6px;
  color: #fff;
  font-family: var(--headline);
  font-size: 17px;
  letter-spacing: -0.03em;
}
.timeline-card {
  min-width: 0;
  overflow-x: clip;
  margin-top: 22px;
}
.timeline-list {
  min-width: 0;
  max-width: 100%;
  position: relative;
}
.timeline-list::before {
  content: "";
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 18px;
  width: 1px;
  background: linear-gradient(180deg, rgba(64, 71, 82, 0.2), rgba(64, 71, 82, 0.5), rgba(64, 71, 82, 0.2));
}
.message-card {
  position: relative;
  min-width: 0;
  max-width: 100%;
  margin-left: 42px;
  padding: 18px;
}
.message-card::before {
  content: "";
  position: absolute;
  top: 22px;
  left: -32px;
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--surface-4);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 0 0 6px rgba(18, 20, 22, 0.72);
}
.message-card.assistant::before {
  background: var(--success);
  box-shadow: 0 0 0 6px rgba(18, 20, 22, 0.72), 0 0 16px rgba(223, 237, 0, 0.35);
}
.message-card.tool::before {
  background: var(--primary-strong);
  box-shadow: 0 0 0 6px rgba(18, 20, 22, 0.72), 0 0 16px rgba(38, 148, 246, 0.3);
}
.message-card.user::before {
  background: #ffd79d;
}
.message-card.system::before {
  background: var(--muted);
}
.message-head {
  display: flex;
  min-width: 0;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 12px;
}
.step-title {
  display: grid;
  min-width: 0;
  gap: 5px;
}
.step-title strong {
  font-size: 18px;
  color: #fff;
  letter-spacing: -0.03em;
}
.message-body {
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  color: var(--muted-2);
  line-height: 1.62;
}
.tool-call-list {
  display: grid;
  min-width: 0;
  max-width: 100%;
  gap: 10px;
  margin-top: 14px;
}
.tool-pill-row {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 8px;
}
.tool-pill-row > * {
  min-width: 0;
}
.meta-row > * {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.empty {
  padding: 16px;
  border-radius: 16px;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  color: var(--muted);
  background: rgba(12, 14, 16, 0.42);
}
.hidden {
  display: none;
}
@media (max-width: 1280px) {
  .command-kpis {
    grid-template-columns: repeat(3, minmax(110px, 1fr));
  }
  .hero-grid,
  .hero-footer {
    grid-template-columns: 1fr;
  }
  .metric-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
@media (max-width: 980px) {
  .app {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: static;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--line-soft);
  }
  .command-bar {
    position: static;
  }
}
@media (max-width: 760px) {
  .content,
  .command-bar {
    padding-left: 16px;
    padding-right: 16px;
  }
  .rail-header {
    padding-left: 16px;
    padding-right: 16px;
  }
  .case-rail {
    padding-left: 10px;
    padding-right: 10px;
  }
  .command-title h1 {
    font-size: 28px;
  }
  .command-kpis,
  .metric-grid,
  .trace-grid,
  .rail-summary {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 560px) {
  .command-kpis,
  .metric-grid,
  .trace-grid,
  .rail-summary {
    grid-template-columns: 1fr;
  }
  .hero,
  .panel,
  .timeline-card,
  .message-card {
    padding: 16px;
  }
  .message-card {
    margin-left: 28px;
  }
  .timeline-list::before {
    left: 10px;
  }
  .message-card::before {
    left: -24px;
  }
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="rail-header">
      <div class="brand">
        <span class="eyebrow">Eval Control Room</span>
        <span class="brand-mark">AETHER_EVAL</span>
        <span class="eyebrow" id="run-id"></span>
      </div>
      <div id="rail-summary" class="rail-summary"></div>
      <div class="search-wrap">
        <span class="search-icon">/</span>
        <input id="case-search" class="search-input" type="search" placeholder="SEARCH_CASES">
      </div>
    </div>
    <div class="case-rail">
      <div class="case-section">
        <div class="section-title fail" id="fail-section-title"></div>
        <div class="case-list" id="fail-case-list"></div>
      </div>
      <div class="case-section">
        <div class="section-title pass" id="pass-section-title"></div>
        <div class="case-list" id="pass-case-list"></div>
      </div>
    </div>
  </aside>
  <main class="main">
    <header class="command-bar">
      <div class="command-inner">
        <div class="command-title">
          <span class="eyebrow">Suite Overview</span>
          <h1>CONTROL ROOM</h1>
          <div class="command-meta">
            <span id="run-date"></span>
            <span id="suite-size"></span>
            <span id="viewer-generated"></span>
          </div>
        </div>
        <div id="command-kpis" class="command-kpis"></div>
      </div>
    </header>
    <div class="main-scroll">
      <div class="content">
        <section id="hero" class="hero">
          <div class="hero-grid">
            <div>
              <div class="hero-title">
                <span id="execution-badge" class="chip"></span>
                <span id="repeat-chip" class="chip neutral hidden"></span>
                <span id="stopped-reason" class="chip neutral"></span>
              </div>
              <div class="eyebrow">Selected Execution</div>
              <h2 id="execution-title"></h2>
              <div class="prompt-block">
                <div class="detail-label">Prompt Input</div>
                <p id="question" class="prompt-text"></p>
              </div>
            </div>
            <div class="metric-grid" id="execution-summary"></div>
          </div>
          <div class="hero-footer">
            <div id="failure-strip" class="failure-strip"></div>
            <div class="timeline-meter">
              <div class="meter-row">
                <span>Start</span>
                <span id="meter-label"></span>
                <span id="meter-end"></span>
              </div>
              <div class="meter-bar">
                <div id="meter-fill" class="meter-fill"></div>
                <div id="meter-marker" class="meter-marker"></div>
              </div>
            </div>
          </div>
        </section>

        <div class="panel-grid">
          <div class="panel-stack">
            <section class="panel">
              <div class="panel-header">
                <div>
                  <div class="eyebrow">Response</div>
                  <h3>Final Answer</h3>
                </div>
                <div class="tool-pill-row">
                  <label id="repeat-label" class="eyebrow hidden" for="repeat-select">Repeat</label>
                  <select id="repeat-select" class="hidden"></select>
                </div>
              </div>
              <div id="final-answer" class="answer-text"></div>
              <div id="error-box"></div>
            </section>
          </div>

          <div class="panel-stack">
            <div class="evidence-grid">
              <section class="evidence-card accent">
                <div class="card-inner">
                  <div class="panel-header">
                    <div>
                      <div class="eyebrow">Sources</div>
                      <h3>Citations</h3>
                    </div>
                    <span id="citation-count" class="eyebrow"></span>
                  </div>
                  <div id="citations" class="citation-list"></div>
                </div>
              </section>

              <section class="evidence-card primary">
                <div class="card-inner">
                  <div class="panel-header">
                    <div>
                      <div class="eyebrow">Scoring</div>
                      <h3>Metric Breakdown</h3>
                    </div>
                    <span class="eyebrow">Failures First</span>
                  </div>
                  <div id="metrics" class="metrics-list"></div>
                </div>
              </section>

              <section class="evidence-card">
                <div class="card-inner">
                  <div class="panel-header">
                    <div>
                      <div class="eyebrow">Saved Files</div>
                      <h3>Artifacts</h3>
                    </div>
                    <span class="eyebrow">Trace Bundle</span>
                  </div>
                  <div id="artifacts" class="artifact-list"></div>
                </div>
              </section>

              <section class="evidence-card alert">
                <div class="card-inner">
                  <div class="panel-header">
                    <div>
                      <div class="eyebrow">Advanced</div>
                      <h3>Execution Meta</h3>
                    </div>
                    <span class="eyebrow">Raw Inspection</span>
                  </div>
                  <div id="trace-grid" class="trace-grid"></div>
                  <details class="drawer" id="normalized-drawer">
                    <summary>Normalized Trace</summary>
                    <pre id="normalized-content"></pre>
                  </details>
                </div>
              </section>
            </div>
          </div>
        </div>

        <section class="timeline-card">
          <div class="panel-header">
            <div>
              <div class="eyebrow">Evidence Trail</div>
              <h3>Message Timeline</h3>
            </div>
            <span id="timeline-meta" class="eyebrow"></span>
          </div>
          <div id="timeline" class="timeline-list"></div>
        </section>
      </div>
    </div>
  </main>
</div>
<script id="run-data" type="application/json">__RUN_DATA_JSON__</script>
<script>
const payload = JSON.parse(document.getElementById("run-data").textContent);
const state = { caseIndex: 0, repeatIndex: 0, query: "" };

const byId = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => (
  {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[char]
));
const prettyJson = (value) => JSON.stringify(value ?? null, null, 2);

function init() {
  byId("run-id").textContent = payload.suite_run_id || "unknown_run";
  const firstFail = payload.cases.findIndex((item) => !item.overall_passed);
  state.caseIndex = firstFail >= 0 ? firstFail : 0;
  bindSearch();
  renderChrome();
  renderCaseLists();
  renderMain();
}

function bindSearch() {
  const input = byId("case-search");
  input.addEventListener("input", (event) => {
    state.query = String(event.target.value || "").trim().toLowerCase();
    renderCaseLists();
  });
}

function renderChrome() {
  const summary = payload.summary || {};
  const failingCases = payload.cases.filter((item) => !item.overall_passed).length;
  const commandStats = [
    { label: "Pass Rate", value: formatPercent(summary.pass_rate), className: "emphasis" },
    { label: "Executions", value: `${summary.passed_executions || 0}/${summary.total_executions || 0}` },
    { label: "Total Cost", value: formatUsd(summary.total_cost_usd || 0) },
    { label: "p95 Latency", value: formatDuration(summary.p95_latency_ms || 0) },
    { label: "Failing Cases", value: String(failingCases), className: failingCases ? "alert" : "emphasis" },
  ];
  byId("command-kpis").innerHTML = commandStats.map((item) => `
    <div class="kpi ${esc(item.className || "")}">
      <span class="label">${esc(item.label)}</span>
      <span class="value">${esc(item.value)}</span>
    </div>
  `).join("");

  const railStats = [
    ["Passed", `${summary.passed_executions || 0}/${summary.total_executions || 0}`],
    ["Mean Tools", formatCompactNumber(summary.mean_tool_calls || 0, 1)],
    ["p50", formatDuration(summary.p50_latency_ms || 0)],
    ["Failing", String(failingCases)],
  ];
  byId("rail-summary").innerHTML = railStats.map(([label, value]) => `
    <div class="mini-stat">
      <span class="label">${esc(label)}</span>
      <span class="value">${esc(value)}</span>
    </div>
  `).join("");

  byId("run-date").textContent = `RUN ${formatDate(summary.created_at_utc || payload.generated_at_utc)}`;
  byId("suite-size").textContent = `${payload.cases.length} CASES`;
  byId("viewer-generated").textContent = `VIEWER ${formatDate(payload.generated_at_utc)}`;
}

function renderCaseLists() {
  const visibleCases = payload.cases
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => !state.query || String(item.case_id || "").toLowerCase().includes(state.query));

  const failing = visibleCases.filter(({ item }) => !item.overall_passed);
  const passing = visibleCases.filter(({ item }) => item.overall_passed);

  byId("fail-section-title").textContent = `Failing Cases (${failing.length})`;
  byId("pass-section-title").textContent = `Passing Cases (${passing.length})`;

  renderCaseListNode(byId("fail-case-list"), failing);
  renderCaseListNode(byId("pass-case-list"), passing);
}

function renderCaseListNode(node, entries) {
  if (!entries.length) {
    node.innerHTML = `<div class="case-item empty-state"><div class="case-title">No matches</div><div class="case-meta">Adjust the case search.</div></div>`;
    return;
  }
  node.innerHTML = entries.map(({ item, index }) => {
    const failCount = item.repeat_count - item.pass_count;
    const selected = index === state.caseIndex ? "active" : "";
    const statusClass = item.overall_passed ? "pass" : "fail";
    const primaryExecution = getExecutionForCase(item, 0);
    return `
      <button class="case-item ${selected} ${statusClass}" data-index="${index}">
        <div class="case-title">${esc(item.case_id)}</div>
        <div class="case-meta">
          <span class="chip ${statusClass}">${item.overall_passed ? "Pass" : "Fail"}</span>
          <span>${esc(`${item.pass_count}/${item.repeat_count} repeats`)}</span>
          ${failCount ? `<span>${esc(`${failCount} failing`)}</span>` : `<span>clean run</span>`}
          <span>${esc(formatDuration(primaryExecution.wall_time_ms || 0))}</span>
        </div>
      </button>
    `;
  }).join("");

  [...node.querySelectorAll(".case-item[data-index]")].forEach((button) => {
    button.addEventListener("click", () => {
      state.caseIndex = Number(button.dataset.index);
      state.repeatIndex = preferredRepeatIndex(payload.cases[state.caseIndex]);
      renderCaseLists();
      renderMain();
    });
  });
}

function renderMain() {
  const caseGroup = payload.cases[state.caseIndex];
  if (!caseGroup) {
    return;
  }

  const repeatSelect = byId("repeat-select");
  const repeatLabel = byId("repeat-label");
  const showRepeatSelect = caseGroup.executions.length > 1;
  state.repeatIndex = clamp(preferredRepeatIndex(caseGroup, state.repeatIndex), 0, caseGroup.executions.length - 1);
  repeatSelect.innerHTML = caseGroup.executions.map((execution, index) => `
    <option value="${index}">r${execution.repeat_index}</option>
  `).join("");
  repeatSelect.value = String(state.repeatIndex);
  repeatSelect.onchange = (event) => {
    state.repeatIndex = Number(event.target.value);
    renderMain();
  };
  repeatSelect.classList.toggle("hidden", !showRepeatSelect);
  repeatLabel.classList.toggle("hidden", !showRepeatSelect);

  const execution = caseGroup.executions[state.repeatIndex];
  const failedMetrics = Array.isArray(execution.failed_metrics) ? execution.failed_metrics : [];
  const hero = byId("hero");
  hero.classList.toggle("pass", !!execution.passed);

  byId("execution-title").textContent = `${caseGroup.case_id} / r${execution.repeat_index}`;
  applyChip(byId("execution-badge"), execution.passed ? "pass" : "fail", execution.passed ? "Pass" : "Fail");
  applyChip(byId("stopped-reason"), execution.stopped_reason === "finish" ? "pass" : "warn", execution.stopped_reason || "unknown");

  const repeatChip = byId("repeat-chip");
  repeatChip.textContent = `Repeat ${execution.repeat_index}`;
  repeatChip.className = `chip neutral${showRepeatSelect ? "" : " hidden"}`;

  byId("question").textContent = execution.question || "No question recorded.";
  byId("final-answer").textContent = execution.final_answer || "No final answer recorded.";
  renderExecutionSummary(execution);
  renderFailureStrip(execution, failedMetrics);
  renderTimelineMeter(execution, failedMetrics);
  renderError(execution.error);
  renderCitations(execution.citations || []);
  renderMetrics(execution.metrics || []);
  renderArtifacts(execution.artifacts || {});
  renderTraceMeta(execution);
  renderNormalized(execution.normalized || {});
  renderTimeline(execution.messages || []);
}

function renderExecutionSummary(execution) {
  const tokens = execution.total_tokens || {};
  const totalTokenCount = Number(tokens.input || 0) + Number(tokens.output || 0);
  const stats = [
    ["Latency", formatDuration(execution.wall_time_ms || 0), execution.passed ? "pass" : "fail"],
    ["Tool Calls", String(execution.tool_count || 0), "neutral"],
    ["Metric Failures", String((execution.failed_metrics || []).length), (execution.failed_metrics || []).length ? "fail" : "pass"],
    ["Tokens", totalTokenCount ? formatCompactNumber(totalTokenCount) : "N/A", "neutral"],
  ];

  byId("execution-summary").innerHTML = stats.map(([label, value, tone]) => `
    <div class="metric-card">
      <div class="detail-label">${esc(label)}</div>
      <div class="value ${esc(tone)}">${esc(value)}</div>
    </div>
  `).join("");
}

function renderFailureStrip(execution, failedMetrics) {
  const node = byId("failure-strip");
  if (!failedMetrics.length && !execution.error) {
    node.className = "failure-strip pass";
    node.innerHTML = `
      <div class="detail-label">Status Summary</div>
      <div class="failure-list">
        <div class="failure-item">All metrics passed for this execution.</div>
        <div class="failure-item">No runtime error was recorded in the trace.</div>
      </div>
    `;
    return;
  }

  const lines = [];
  if (execution.error) {
    lines.push(`<div class="failure-item">${esc(execution.error)}</div>`);
  }
  failedMetrics.slice(0, 3).forEach((metric) => {
    lines.push(`<div class="failure-item"><strong>${esc(metric.name || "metric")}</strong>: ${esc(metric.reason || "No reason recorded.")}</div>`);
  });
  node.className = "failure-strip";
  node.innerHTML = `
    <div class="detail-label">What Went Wrong</div>
    <div class="failure-list">${lines.join("")}</div>
  `;
}

function renderTimelineMeter(execution, failedMetrics) {
  const messageCount = Array.isArray(execution.messages) ? execution.messages.length : 0;
  const failRatio = execution.metrics && execution.metrics.length
    ? ((execution.failed_metrics || []).length / execution.metrics.length)
    : 0;
  const markerPercent = execution.passed ? 100 : Math.max(18, Math.round((1 - failRatio) * 100));
  byId("meter-label").textContent = execution.passed ? "CLEAR EXIT" : "FAILURE DETECTED";
  byId("meter-end").textContent = `${formatDuration(execution.wall_time_ms || 0)} / ${messageCount} STEPS`;
  byId("meter-fill").className = `meter-fill${execution.passed ? "" : " fail"}`;
  byId("meter-marker").className = `meter-marker${execution.passed ? "" : " fail"}`;
  byId("meter-marker").style.left = `${markerPercent}%`;
}

function renderError(errorText) {
  const node = byId("error-box");
  if (!errorText) {
    node.innerHTML = "";
    return;
  }
  node.innerHTML = `
    <div class="error-box">
      <div class="detail-label">Runtime Error</div>
      <div class="answer-text">${esc(errorText)}</div>
    </div>
  `;
}

function renderCitations(citations) {
  byId("citation-count").textContent = `${citations.length} total`;
  if (!citations.length) {
    byId("citations").innerHTML = `<div class="empty">No citations recorded.</div>`;
    return;
  }
  byId("citations").innerHTML = citations.map((citation, index) => `
    <div class="citation-item">
      <div class="detail-label">Source ${index + 1}</div>
      <a class="citation-link" href="${esc(citation)}">${esc(citation)}</a>
    </div>
  `).join("");
}

function renderMetrics(metrics) {
  if (!metrics.length) {
    byId("metrics").innerHTML = `<div class="empty">No metrics recorded.</div>`;
    return;
  }
  const ordered = [...metrics].sort((a, b) => Number(a.passed) - Number(b.passed));
  byId("metrics").innerHTML = ordered.map((metric) => {
    const css = metric.passed ? "pass" : "fail";
    const score = clamp(Number(metric.score || 0), 0, 1);
    const details = metric.details && Object.keys(metric.details).length
      ? `<details class="drawer"><summary>Metric Details</summary><pre>${esc(prettyJson(metric.details))}</pre></details>`
      : "";
    return `
      <div class="metric-item ${css}">
        <div class="metric-head">
          <div>
            <p class="metric-name">${esc(metric.name || "metric")}</p>
            <div class="meta-row">
              <span>${esc(metric.kind || "unknown")}</span>
              <span>${esc(formatDuration(metric.latency_ms || 0))}</span>
            </div>
          </div>
          <span class="chip ${css}">${metric.passed ? "Pass" : "Fail"}</span>
        </div>
        <p class="metric-reason">${esc(metric.reason || "No reason recorded.")}</p>
        <div class="metric-bar"><span style="width:${Math.max(score * 100, 6)}%"></span></div>
        <div class="meta-row">
          <span>score ${esc(score.toFixed(2))}</span>
          <span>${esc(metric.cost_usd ? formatUsd(metric.cost_usd) : "$0.0000")}</span>
        </div>
        ${details}
      </div>
    `;
  }).join("");
}

function renderArtifacts(artifacts) {
  const entries = Object.entries(artifacts || {});
  if (!entries.length) {
    byId("artifacts").innerHTML = `<div class="empty">No artifacts recorded.</div>`;
    return;
  }
  byId("artifacts").innerHTML = entries.map(([label, value]) => `
    <div class="artifact-item">
      <div class="detail-label">${esc(label)}</div>
      <code>${esc(value)}</code>
    </div>
  `).join("");
}

function renderTraceMeta(execution) {
  const tokens = execution.total_tokens || {};
  const totalTokenCount = Number(tokens.input || 0) + Number(tokens.output || 0);
  const meta = [
    ["Model", execution.model || "N/A"],
    ["Run Id", execution.run_id || "N/A"],
    ["Messages", String(execution.message_count || (execution.messages || []).length || 0)],
    ["Input Tokens", tokens.input ? formatCompactNumber(tokens.input) : "N/A"],
    ["Output Tokens", tokens.output ? formatCompactNumber(tokens.output) : "N/A"],
    ["Total Tokens", totalTokenCount ? formatCompactNumber(totalTokenCount) : "N/A"],
  ];
  byId("trace-grid").innerHTML = meta.map(([label, value]) => `
    <div class="trace-item">
      <div class="detail-label">${esc(label)}</div>
      <div class="value">${esc(value)}</div>
    </div>
  `).join("");
}

function renderNormalized(normalized) {
  const drawer = byId("normalized-drawer");
  const content = byId("normalized-content");
  const hasNormalized = normalized && Object.keys(normalized).length;
  drawer.classList.toggle("hidden", !hasNormalized);
  if (hasNormalized) {
    content.textContent = prettyJson(normalized);
  }
}

function renderTimeline(messages) {
  byId("timeline-meta").textContent = `${messages.length} steps`;
  if (!messages.length) {
    byId("timeline").innerHTML = `<div class="empty">No messages recorded.</div>`;
    return;
  }

  byId("timeline").innerHTML = messages.map((message, index) => {
    const role = String(message.role || "unknown");
    const roleClass = roleClasses(role);
    const latency = message.latency_ms != null ? formatDuration(message.latency_ms) : "";
    return `
      <article class="message-card ${esc(roleClass)}">
        <div class="message-head">
          <div class="step-title">
            <span class="eyebrow">Step ${index + 1}</span>
            <strong>${esc(roleLabel(role))}</strong>
          </div>
          <div class="tool-pill-row">
            ${rolePill(role)}
            ${latency ? `<span class="chip neutral">${esc(latency)}</span>` : ""}
          </div>
        </div>
        ${renderMessageBody(message)}
      </article>
    `;
  }).join("");
}

function renderMessageBody(message) {
  if (message.role === "assistant") {
    const text = message.text
      ? `<div class="message-body">${escapeMultiline(message.text)}</div>`
      : `<div class="empty">No assistant text.</div>`;
    const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
    const tools = toolCalls.length ? `
      <div class="tool-call-list">
        ${toolCalls.map((toolCall, index) => `
          <details class="tool-drawer">
            <summary>${esc(toolCall.name || `tool_call_${index + 1}`)}</summary>
            <pre>${esc(prettyJson({
              id: toolCall.id || null,
              args: toolCall.args || {},
            }))}</pre>
          </details>
        `).join("")}
      </div>
    ` : "";
    return `${text}${tools}`;
  }

  if (message.role === "tool") {
    const meta = `
      <div class="meta-row">
        <span>${esc(message.name || "tool")}</span>
        ${message.tool_use_id ? `<span>${esc(message.tool_use_id)}</span>` : ""}
      </div>
    `;
    return `
      ${meta}
      <details class="drawer" open>
        <summary>Tool Output</summary>
        <pre>${esc(prettyJson(message.content))}</pre>
      </details>
    `;
  }

  return `<div class="message-body">${renderStructuredContent(message.content)}</div>`;
}

function renderStructuredContent(value) {
  if (value == null || value === "") {
    return "No content recorded.";
  }
  if (typeof value === "string") {
    return escapeMultiline(value);
  }
  return `<pre>${esc(prettyJson(value))}</pre>`;
}

function escapeMultiline(value) {
  return esc(String(value ?? "")).replace(/\\n/g, "<br>");
}

function applyChip(node, tone, text) {
  node.textContent = text;
  node.className = `chip ${tone}`;
}

function roleLabel(role) {
  return {
    assistant: "Assistant Reasoning",
    tool: "Tool Result",
    user: "User Prompt",
    system: "System Prompt",
  }[role] || role;
}

function roleClasses(role) {
  return {
    assistant: "assistant",
    tool: "tool",
    user: "user",
    system: "system",
  }[role] || "system";
}

function rolePill(role) {
  const tone = {
    assistant: "pass",
    tool: "neutral",
    user: "warn",
    system: "system",
  }[role] || "system";
  return `<span class="chip ${tone}">${esc(role)}</span>`;
}

function getExecutionForCase(caseGroup, fallbackIndex) {
  const failedIndex = caseGroup.executions.findIndex((item) => !item.passed);
  return failedIndex >= 0 ? caseGroup.executions[failedIndex] : caseGroup.executions[fallbackIndex || 0];
}

function preferredRepeatIndex(caseGroup, currentIndex) {
  if (typeof currentIndex === "number" && currentIndex >= 0 && currentIndex < caseGroup.executions.length) {
    return currentIndex;
  }
  const failedIndex = caseGroup.executions.findIndex((item) => !item.passed);
  return failedIndex >= 0 ? failedIndex : 0;
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatUsd(value) {
  return `$${Number(value || 0).toFixed(4)}`;
}

function formatDuration(value) {
  const numeric = Number(value || 0);
  if (!numeric) {
    return "0ms";
  }
  if (numeric >= 1000) {
    return `${(numeric / 1000).toFixed(1)}s`;
  }
  return `${Math.round(numeric)}ms`;
}

function formatCompactNumber(value, digits = 0) {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: digits }).format(Number(value || 0));
}

function formatDate(value) {
  if (!value) {
    return "UNKNOWN";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).toUpperCase();
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

init();
</script>
</body>
</html>
"""
    return template.replace("__RUN_DATA_JSON__", run_data_json)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative_artifact_path(run_dir: Path, absolute_path: Path) -> str:
    try:
        return str(absolute_path.relative_to(run_dir))
    except ValueError:
        return str(absolute_path)


def _resolve_artifact_path(run_dir: Path, value: Any, fallback: Path) -> Path:
    if isinstance(value, str) and value:
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return (run_dir / candidate).resolve()
    return fallback


def _execution_key(case_id: str, repeat_index: int) -> str:
    return f"{case_id}__r{repeat_index}"


def _utc_now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.isoformat().replace("+00:00", "Z")
