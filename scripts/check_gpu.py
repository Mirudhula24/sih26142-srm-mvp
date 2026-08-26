"""Confirm the GPU is usable and report the real VRAM headroom for SRM inference.

Run this first on any new machine -- inside the container as well as on the host, since
those answer differently when the NVIDIA runtime is not wired up:

    python scripts/check_gpu.py
    docker compose run --rm ml_worker python scripts/check_gpu.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml_engine"))

VRAM_BUDGET_GB = 8.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=256, help="Coarse tile size to probe.")
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()

    import numpy as np
    import torch

    print(f"torch            : {torch.__version__}")
    print(f"cuda available   : {torch.cuda.is_available()}")

    if not torch.cuda.is_available():
        print(f"cuda build       : {torch.version.cuda}")
        print(
            "\nNo GPU visible. On the host that usually means a CPU-only torch build; "
            "inside a container it usually means the NVIDIA runtime is not registered.\n"
            "See docs/GPU_SETUP.md. The CPU path still works:\n"
            "  docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build"
        )
        return 1

    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(0)
    total_gb = props.total_memory / 1024**3
    print(f"device           : {props.name}")
    print(f"capability       : sm_{props.major}{props.minor}")
    print(f"total VRAM       : {total_gb:.1f} GB")
    print(f"cuda runtime     : {torch.version.cuda}")

    import inference

    model, _ = inference.load_model(
        os.environ.get("MODEL_WEIGHTS_PATH"), device="cuda", scale_factor=args.scale
    )

    torch.cuda.reset_peak_memory_stats()
    tensor = np.random.rand(6, args.size, args.size).astype(np.float32)
    result = inference.run_srm(tensor, model, device, scale_factor=args.scale,
                               patch=args.size)
    peak_gb = torch.cuda.max_memory_allocated() / 1024**3

    print(f"\n{args.size}x{args.size} tile at {args.scale}x")
    print(f"  latency        : {result['execution_time_seconds']:.2f} s")
    print(f"  peak VRAM      : {peak_gb:.2f} GB of {total_gb:.1f} GB")
    print(f"  mass error     : {result['mass_conservation_error']:.2e}")

    if peak_gb > VRAM_BUDGET_GB:
        print(f"\nOver the {VRAM_BUDGET_GB:.0f} GB design budget. Lower MAX_PATCH_SIZE "
              f"(e.g. 128) -- the patch loop stitches tiles back together.")
        return 1
    if peak_gb > total_gb * 0.8:
        print("\nClose to this card's limit. Lower MAX_PATCH_SIZE if a larger AOI OOMs.")
    print("\nGPU path looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
