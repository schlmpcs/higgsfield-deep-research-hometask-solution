"""CLI entrypoint for the Deep Research Lite eval framework.

Phase 1 intentionally wires only case loading and command shapes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from .judge_client import score_saved_trace
from .loader import DEFAULT_CASES_DIR, CaseLoadError
from .reporting import load_diff, render_diff, render_run_summary
from .runner import execute_run, plan_run, replay_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.cli",
        description="Minimal file-based evaluation framework for Deep Research Lite.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Load cases and prepare a suite run.")
    run_parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help="Directory containing *.yaml, *.yml, or *.json eval case files.",
    )
    run_parser.add_argument("--case", help="Run only one case id.")
    run_parser.add_argument(
        "--repeats",
        type=_positive_int,
        default=1,
        help="Number of repeats per case.",
    )
    run_parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help="Planned worker count for future execution phases.",
    )
    run_parser.set_defaults(func=_run_command)

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a prior suite run from saved traces.",
    )
    replay_parser.add_argument("--run-id", required=True, help="Suite run id to replay.")
    replay_parser.add_argument(
        "--cases-dir",
        type=Path,
        default=DEFAULT_CASES_DIR,
        help="Directory containing *.yaml, *.yml, or *.json eval case files.",
    )
    replay_parser.set_defaults(func=_replay_command)

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare one suite run with a baseline.",
    )
    diff_parser.add_argument("--run-id", required=True, help="Run id to compare.")
    diff_parser.add_argument("--baseline", required=True, help="Baseline run id.")
    diff_parser.set_defaults(func=_diff_command)

    judge_parser = subparsers.add_parser(
        "judge",
        help="Score one saved trace with one rubric.",
    )
    judge_parser.add_argument("--run-id", required=True, help="Suite run id.")
    judge_parser.add_argument("--case", required=True, help="Case id to score.")
    judge_parser.add_argument(
        "--repeat",
        type=_positive_int,
        default=1,
        help="Repeat index to score.",
    )
    judge_parser.add_argument(
        "--rubric",
        required=True,
        help="Rubric file under evals/rubrics/ or an absolute path.",
    )
    judge_parser.add_argument(
        "--judge-model",
        help="Override the configured judge model for this one command.",
    )
    judge_parser.set_defaults(func=_judge_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2

    try:
        return func(args)
    except (CaseLoadError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run_command(args: argparse.Namespace) -> int:
    run_plan = plan_run(
        cases_dir=args.cases_dir,
        case_id=args.case,
        repeats=args.repeats,
        concurrency=args.concurrency,
    )
    run_paths, _results, summary = execute_run(run_plan)

    print(
        f"Loaded {len(run_plan.cases)} case(s) from {run_plan.cases_dir} "
        f"(repeats={run_plan.repeats}, concurrency={run_plan.concurrency})"
    )
    print(f"Suite run id: {run_paths.suite_run_id}")
    print(f"Run directory: {run_paths.run_dir.resolve()}")
    print(render_run_summary(summary.to_dict()))
    print(f"Evaluations: {run_paths.evaluations_dir.resolve()}")
    print(f"Summary: {run_paths.summary_path.resolve()}")
    print(f"Viewer: {run_paths.viewer_path.resolve()}")
    return 0


def _replay_command(args: argparse.Namespace) -> int:
    run_dir, _results, summary = replay_run(run_id=args.run_id, cases_dir=args.cases_dir)
    print(render_run_summary(summary.to_dict()))
    print(f"Viewer: {(run_dir / 'viewer.html').resolve()}")
    return 0


def _diff_command(args: argparse.Namespace) -> int:
    runs_dir = DEFAULT_CASES_DIR.parent / "runs"
    diff = load_diff(runs_dir / args.run_id, runs_dir / args.baseline)
    print(render_diff(diff))
    return 0


def _judge_command(args: argparse.Namespace) -> int:
    artifact = score_saved_trace(
        run_id=args.run_id,
        case_id=args.case,
        repeat_index=args.repeat,
        rubric_file=args.rubric,
        model=args.judge_model,
    )
    status = "PASS" if artifact.score.passed else "FAIL"
    cache_label = "cache-hit" if artifact.cache_hit else "fresh"
    print(
        f"{status} {args.case} r{args.repeat} "
        f"score={artifact.score.score:.2f} model={artifact.model} [{cache_label}]"
    )
    print(f"reason: {artifact.score.reason}")
    if artifact.score.evidence:
        print("evidence:")
        for item in artifact.score.evidence:
            print(f"- {item}")
    print(f"artifact: {artifact.artifact_path}")
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
