# Radeon MI50 vs RX 7700 XT — stable-diffusion.cpp performance report

Benchmark of the local AI game-art pipeline in `/opt/AssetGeneration`
(stable-diffusion.cpp `master-1088`, commit `32d516c`, Vulkan backend).

- **Host:** AMD Ryzen 5 5600G, 30 GB RAM, Linux `7.0.0-43-generic`
- **Driver:** Mesa RADV 26.0.8, Vulkan
- **Date:** 2026-11-15
- **Cards tested:**
  - **AMD Radeon Instinct MI50 32 GB** — `gfx906` / VEGA20, 32 GB HBM2
  - **AMD Radeon RX 7700 XT** — RDNA3 / NAVI32, 12 GB GDDR6

The integrated Renoir iGPU was **not used** and is blacklisted for the app
through `GGML_VK_VISIBLE_DEVICES=1,2`. With it hidden, the engine maps:

| Card | Engine device | Default |
| --- | --- | --- |
| Radeon Instinct MI50 | `vulkan0` | yes |
| Radeon RX 7700 XT | `vulkan1` | optional |

The default systemd service was restored to the MI50 (`vulkan0`) after testing.

## Method

- Models:
  - **SDXL:** `Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors` + `sdxl-vae-fp16-fix`
  - **SD1.5:** `epicphotogasm_v1.safetensors`
- Same prompt and seed (`42`) for every run; `dpm++2m` sampler, `karras`
  scheduler, CFG 6.5, batch 1, VAE tiling enabled.
- IP-Adapter was **not** loaded during benchmarks so the model footprint is
  directly comparable between cards.
- One warmup run discarded; results are the median of 3 measured runs
  (SDXL 30-step and dual-GPU rows: 2 runs).
- `Sampling` and `Decode` are engine-reported phase times. `Job wall` is the full
  HTTP job: conditioning + sampling + VAE decode.
- Peak VRAM read from `/sys/class/drm/*/device/mem_info_vram_used`.
- Output PNGs were decoded and checked to be non-blank.

## Single-card results

| Model | Resolution | Steps | Card | Sampling | s/step | Decode | Job wall | Peak VRAM |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| SDXL Juggernaut v9 | 1024² | 20 | MI50 | 47.06 s | 2.35 | 6.74 s | **54.17 s** | 6.5 GB |
| SDXL Juggernaut v9 | 1024² | 20 | RX 7700 XT | 18.95 s | 0.95 | 3.77 s | **23.08 s** | 6.6 GB |
| SDXL Juggernaut v9 | 1024² | 30 | MI50 | 68.58 s | 2.29 | 6.51 s | **75.35 s** | 6.5 GB |
| SDXL Juggernaut v9 | 1024² | 30 | RX 7700 XT | 28.40 s | 0.95 | 3.78 s | **32.48 s** | 6.6 GB |
| SD1.5 epicphotogasm | 512² | 20 | MI50 | 5.74 s | 0.29 | 1.03 s | **7.02 s** | 2.0 GB |
| SD1.5 epicphotogasm | 512² | 20 | RX 7700 XT | 3.67 s | 0.18 | 0.70 s | **4.52 s** | 2.1 GB |

### Findings

- **RX 7700 XT is much faster:** ~**2.35×** faster end-to-end at SDXL 1024²/20
  steps (23.1 s vs 54.2 s) and ~**2.3×** at the app-default 30 steps (32.5 s vs
  75.4 s). SD1.5 is ~**1.55×** faster (4.5 s vs 7.0 s).
- VAE decode is also ~1.8× faster on the 7700 XT (3.8 s vs 6.7 s at 1024²).
- SDXL peak VRAM is ~6.5 GB on either card, so the current 1024² workflows
  **fit comfortably on the 12 GB 7700 XT**.
- The MI50 has an independent cooler/controller, so its fan RPM is not
  externally readable — only temperature. Under sustained SDXL load it was
  observed around **70–73 °C**, and it settles slower than its first cool run
  (37.6 s → ~47 s sampling), giving roughly **±10–15 % run-to-run variance**.
  The 7700 XT was stable to <1 %.

## Both cards on one task (single-job layer split)

Command shape:

```bash
--backend "vulkan0&vulkan1" --split-mode layer
```

This genuinely splits the U-Net across both cards. The split is proportional to
memory budget (~80/20), not to card speed; VAE stays on one GPU.

| Workload | MI50 alone | RX 7700 XT alone | Dual split | vs MI50 | vs 7700 XT |
| --- | ---: | ---: | ---: | ---: | ---: |
| SDXL 1024²/20 (memory-proportional split) | 54.17 s | 23.08 s | 41.17 s | 1.32× faster | **1.78× slower** |
| SDXL 1024²/20 (biased `--max-vram vulkan0=5,vulkan1=11`) | 54.17 s | 23.08 s | 34.89 s¹ | 1.55× faster | **1.51× slower** |
| SD1.5 512²/20 | 7.02 s | 4.52 s | 6.78 s | ~1.04× | **1.50× slower** |

¹ one measured run.

**Verdict: do not split a single job across these cards.** The GPUs are
heterogeneous, the layer split follows memory rather than throughput, and
cross-device activations travel through host memory (no P2P). A single task can
never beat the fastest participating card and pays extra transfer overhead.
Biasing more layers onto the 7700 XT helps, but still loses to the 7700 XT alone.

## Both cards, two jobs in parallel (recommended)

Run **two `sd-server` instances**, one per GPU, and submit independent jobs
concurrently. Measured with SDXL 1024²/20 steps, one job per card:

| Mode | Pair wall time | Speedup |
| --- | ---: | ---: |
| Sequential (MI50, then 7700 XT) | 69.48 s | 1.00× |
| Parallel (both cards at once) | 47.17 s | **1.47×** |

Per-job latency is unchanged (MI50 ~46.9 s, RX 7700 XT ~22.9 s). This is the
practical way to use both cards: throughput scales for batches of independent
assets; a single asset does not get faster.

## Recommendations

1. **Keep the MI50 as the default** (as configured) for 32 GB headroom, or
   switch interactive SDXL work to the RX 7700 XT for ~2.3–2.5× lower latency:
   ```bash
   scripts/start-server.sh <checkpoint> vulkan1
   # or set config.json -> engine.backend to vulkan1 and restart the service
   ```
2. **For throughput, run two servers** — e.g. the normal service on port 1234
   (MI50) plus a second `sd-server` on port 1235 bound to the 7700 XT — and feed
   independent jobs to both. The current `assetgen.py` targets one server, so
   parallel use is a two-worker/manual setup.
3. **Never use single-task layer splitting** between the MI50 and 7700 XT.
4. Keep VAE tiling enabled at ≥1024²; it is required for a correct decode on
   this RADV driver.

## Reproducing

Harnesses added under `/opt/AssetGeneration/scripts/`:

```bash
cd /opt/AssetGeneration

# single card
scripts/gpu-benchmark.py --name mi50-sdxl --backend vulkan0 \
  --checkpoint Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors \
  --width 1024 --height 1024 --steps 20 --runs 3

scripts/gpu-benchmark.py --name rx7700xt-sdxl --backend vulkan1 \
  --checkpoint Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors \
  --width 1024 --height 1024 --steps 20 --runs 3

# single task split across both cards
scripts/gpu-benchmark.py --name dual-sdxl --backend 'vulkan0&vulkan1' \
  --split-mode layer \
  --checkpoint Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors \
  --width 1024 --height 1024 --steps 20 --runs 2

# two jobs in parallel, one per card
scripts/gpu-parallel-benchmark.py
```

Raw JSON results and generated benchmark images are in
`/opt/AssetGeneration/game-art/logs/benchmarks/`.

## Configuration changes made

- Renoir iGPU blacklisted app-wide: `scripts/device-env.sh` exports
  `GGML_VK_VISIBLE_DEVICES=1,2`; all server/CLI scripts source it and the
  systemd unit sets it too.
- `config/config.json`: default backend remapped to `vulkan0` (MI50), with
  `visible_devices` and a `devices` map documenting both cards.
- `scripts/start-server.sh` accepts an optional backend argument (defaults to
  the config backend), for easy switching or dual-card experiments.
- `/opt/AssetGeneration/README.md` left unchanged.
