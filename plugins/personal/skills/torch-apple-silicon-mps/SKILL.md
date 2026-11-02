---
name: torch-apple-silicon-mps
description: What's actually true about running torch/transformers on Apple Silicon (MPS backend, Rosetta 2, fork-safety) — findings from live-benchmarking and live-testing against a real fork-per-request service (guard-service), not assumptions.
---

# torch on Apple Silicon — MPS, Rosetta, fork-safety

Findings from actually benchmarking and testing torch/transformers on an
M-series Mac against the `guard-service` prompt-injection service (a FastAPI app
that forks a child process per request). Apply these whenever advising on
local dev perf for a torch/transformers service on Apple Silicon — don't
re-derive or re-assume, but do re-verify if the claim is load-bearing for a
decision (torch/transformers versions move fast).

## MPS is real and fast — confirmed via `scripts/bench_device.py`-style benchmark

Apple's Metal (MPS) backend measurably beats CPU inference for a small
(Qwen3-0.6B-class) transformer classifier on an M-series Mac: roughly
**4-5x** in one measured run (short text 0.141s→0.046s, a 15x-repeated text
1.99s→0.41s). Use `torch.float32` on MPS, not `bfloat16` — MPS bf16 support
has historically been inconsistent across torch versions (unlike CPU/CUDA).
Always benchmark on the actual current torch version before trusting a
number from a prior session; MPS support matures release to release.

## Rosetta 2 is irrelevant to native MPS/ARM64 torch

No translation is involved running natively-built ARM64 PyTorch with MPS —
Rosetta only matters for running an `x86_64` (`--platform linux/amd64`)
Docker image *accelerated* instead of falling back to slow QEMU emulation.
That's a useful lever for testing closer to a real x86_64 prod node from an
Apple Silicon dev machine, but it has nothing to do with MPS itself.

## MPS is NOT fork-safe — confirmed via live crash reproduction

**This is the load-bearing finding.** A process that has initialized an MPS
(Metal) context and then `fork()`s produces a child that crashes
immediately if it touches the inherited GPU context — confirmed
empirically: `EOFError` on a result pipe, no Python-level traceback, same
crash signature as an unrelated macOS-only fork crash also found this
session (forking a torch/transformers process on macOS crashes on
sufficiently large inputs — confirmed NOT to reproduce on real Linux/aarch64
containers; a Darwin-specific fork quirk, separate from the MPS issue but
easy to conflate since the failure signature is identical).

**Consequence**: any service architecture that forks a child process to run
inference per-request (e.g. for hard process-kill cancellation on
disconnect/deadline — see the `guard-service` process-kill design)
**cannot** also offer a live MPS device toggle. The two are structurally
incompatible, not just under-tested — every accepted request would crash.
Don't propose `GUARD_SERVICE_DEVICE_OVERRIDE=mps`-style env toggles for a
fork-per-request service; this was implemented, live-tested, and reverted
in exactly this session for exactly this reason.

**What's still fine**: MPS works completely normally in a process that
never forks — a standalone benchmark/experimentation script run directly
(`python scripts/bench_device.py`), a Jupyter-style local exploration
session, or a service architecture that doesn't fork per request at all.
The fork-safety problem is specific to fork-per-request architectures, not
to MPS or torch in general.

## How to advise

- If asked "should we make MPS a runtime option" for a service that forks
  per request: no — explain the fork-safety conflict above, offer a
  standalone benchmark script as the local-dev-only alternative instead.
- If asked "is Apple Silicon worth benchmarking" for local dev iteration
  speed (not the deployed service): yes, real and worth it — but always
  re-run the benchmark on the current torch version rather than quoting old
  numbers, since MPS support and torch's CPU fallback behavior (see the
  separate `mkldnn_matmul`/bf16 CPU regression note in any per-repo
  torch-pin comments) both move fast across versions.
- Never assume Rosetta is needed for MPS/ARM64 torch — only mention it if
  the actual ask is about running an x86_64 container.
