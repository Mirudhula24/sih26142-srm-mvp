"""Fetch a pre-trained Sentinel-2 super-resolution backbone into ml_engine/weights/.

SEN2SRLite (ESAOpenSR / Taco Foundation) is the default: it is purpose-built for
Sentinel-2 at a 4x factor, which matches our S = 4 target, and runs in under 5 s a tile.

    pip install sen2sr mlstac
    python scripts/download_weights.py
"""
import argparse
import os
import sys

DEFAULT_URL = (
    "https://huggingface.co/tacofoundation/sen2sr/resolve/main/"
    "SEN2SRLite/NonReference_RGBN_x4/mlm.json"
)
DEFAULT_OUT = os.path.join("ml_engine", "weights", "SEN2SRLite_RGBN")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    try:
        import mlstac
    except ImportError:
        print("mlstac is not installed. Run: pip install sen2sr mlstac", file=sys.stderr)
        return 1

    os.makedirs(args.out, exist_ok=True)
    mlstac.download(file=args.url, output_dir=args.out)
    print(f"Downloaded to {args.out}")
    print("Load with: mlstac.load(path).compiled_model(device='cuda')")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
