from __future__ import annotations

import argparse
import json

from ecocommit.checkpoint_d_workflow import (
    CheckpointDSimulatedWorkflow,
    SimulationScenario,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the deterministic Checkpoint D synthetic workflow. "
            "This never calls a real payment provider and is not checkpoint evidence."
        )
    )
    parser.add_argument(
        "--scenario",
        choices=[item.value for item in SimulationScenario],
        default=SimulationScenario.HAPPY_PATH.value,
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    result = CheckpointDSimulatedWorkflow().run(args.scenario)
    print(
        json.dumps(
            result,
            indent=None if args.compact else 2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
