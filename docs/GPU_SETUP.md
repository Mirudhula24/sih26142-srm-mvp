# GPU setup

The inference worker needs the container to see the host GPU. Everything else in the
stack is plain CPU work.

## Target hardware

| Card | VRAM | Verdict |
|---|---|---|
| RTX 3080 / 3080 Ti | 10–12 GB | Comfortable. Meets the 8 GB budget with headroom. |
| RTX 3090 / 4090 | 24 GB | Comfortable. The 5 s figure in the benchmarks table is a 3090. |
| NVIDIA T4 / A10G | 16–24 GB | Comfortable. T4 is the 8 s reference. |
| RTX 2060 / 3060 laptop | 6 GB | Works at `MAX_PATCH_SIZE=128`. |
| MX250 / MX350 and similar | 2 GB | Use the CPU override instead. |

An RTX 3080 is compute capability `sm_86`, fully covered by the CUDA 12.1 wheels the
`ml_engine` image pins. Nothing needs changing for it — the default
`docker compose up --build` is the right command.

## One-time host setup

**Linux.** Install the NVIDIA driver, then the container toolkit:

```bash
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**Windows.** Install the current NVIDIA driver on Windows itself (not inside WSL), then
enable the WSL2 backend in Docker Desktop under *Settings → General*. Docker Desktop
ships the GPU plumbing; no toolkit install is needed inside the distro.

## Verify, in order

Each step isolates a different failure.

```bash
# 1. Host sees the card
nvidia-smi

# 2. Docker can pass it through
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 3. Our image sees it, and the model actually fits
docker compose run --rm ml_worker python scripts/check_gpu.py
```

Step 3 prints the device name, peak VRAM for a 256×256 tile, inference latency and the
mass-conservation error, and tells you to lower `MAX_PATCH_SIZE` if it is tight.

## Troubleshooting

**`could not select device driver "nvidia" with capabilities: [[gpu]]`**
The toolkit is not registered with Docker. Re-run the `nvidia-ctk` step above, or on
Windows confirm Docker Desktop is on the WSL2 backend. To keep working meanwhile:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build
```

**`torch.cuda.is_available()` is `False` inside the container**
Usually a CPU-only torch wheel. The GPU image installs from the CUDA index; check you
did not build with `Dockerfile.cpu` by accident (`docker compose config | grep dockerfile`).

**`CUDA out of memory`**
Lower the tile size — the patch loop stitches results back together, so this costs
latency but not correctness:

```bash
MAX_PATCH_SIZE=128 docker compose up -d ml_worker
```

**Inference is slow on the first request only**
Expected. The model is a lazy singleton, so the first job pays for weight loading and
CUDA context creation. Warm it with `scripts/check_gpu.py` before a demo.

**The card is visible but the worker still runs on CPU**
Check `DEVICE` in `.env` — the CPU override sets `DEVICE=cpu`, and an override left in
place from an earlier run will silently win.
