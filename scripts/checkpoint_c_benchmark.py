from __future__ import annotations

import argparse

from ecocommit.checkpoint_c_runner import (
    artifact_receipt,
    load_plan,
    load_suite,
    run_benchmark,
    write_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run pre-registered deterministic Checkpoint C baselines and write a "
            "PRELIMINARY_NOT_FINAL artifact"
        )
    )
    parser.add_argument("--plan", required=True, help="Checkpoint C benchmark plan JSON")
    parser.add_argument("--suite", required=True, help="Checkpoint C scenario suite JSON")
    parser.add_argument("--output", required=True, help="Destination artifact JSON")
    parser.add_argument(
        "--code-revision",
        required=True,
        help="Immutable source revision recorded as provenance (never inferred)",
    )
    parser.add_argument(
        "--working-tree-state",
        required=True,
        choices=("clean", "dirty"),
        help="Explicit source-tree state recorded with the run",
    )
    args = parser.parse_args()

    plan = load_plan(args.plan)
    suite = load_suite(args.suite)
    artifact = run_benchmark(
        plan,
        suite,
        code_revision=args.code_revision,
        working_tree_dirty=args.working_tree_state == "dirty",
    )
    destination = write_artifact(artifact, args.output)
    print(artifact_receipt(artifact, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
