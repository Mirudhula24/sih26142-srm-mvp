"""Time the inference path against the acceptance benchmarks.

    python scripts/benchmark.py --size 256 --runs 5
"""
import argparse
import os
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml_engine"))

import inference  # noqa: E402

LATENCY_BUDGET_S = 8.0
MASS_BUDGET = 1e-3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--weights", default=os.environ.get("MODEL_WEIGHTS_PATH"))
    args = parser.parse_args()

    model, device = inference.load_model(args.weights, scale_factor=args.scale)
    tensor = np.random.rand(6, args.size, args.size).astype(np.float32)

    print(f"device={device}  tile={args.size}x{args.size}  scale={args.scale}x")
    inference.run_srm(tensor, model, device, scale_factor=args.scale)  # warm-up

    times, mass_errors = [], []
    for i in range(args.runs):
        result = inference.run_srm(tensor, model, device, scale_factor=args.scale)
        times.append(result["execution_time_seconds"])
        mass_errors.append(result["mass_conservation_error"])
        print(f"  run {i + 1}: {times[-1]:.3f}s  mass_err={mass_errors[-1]:.2e}")

    median = statistics.median(times)
    worst_mass = max(mass_errors)
    print(f"\nmedian latency : {median:.3f}s  (budget {LATENCY_BUDGET_S}s) "
          f"{'PASS' if median < LATENCY_BUDGET_S else 'FAIL'}")
    print(f"max mass error : {worst_mass:.2e}  (budget {MASS_BUDGET:.0e}) "
          f"{'PASS' if worst_mass < MASS_BUDGET else 'FAIL'}")
    return 0 if median < LATENCY_BUDGET_S and worst_mass < MASS_BUDGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
