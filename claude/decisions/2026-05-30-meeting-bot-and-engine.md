# Meeting recording architecture + transcription engine (M4)

**Date**: 2026-05-30
**Decided by**: George (on Claude's analysis)
**Status**: Active. Refines/supersedes 2026-05-30-whisper-engine.md (engine).

## Context
Planning features 2+3 (recording + transcription). Constraints that shaped it:
- EC2 t3.micro can't record: Pycord voice sinks buffer the whole meeting in RAM
  (OOM on 1 GB), 8 GB disk too small, no GPU for Whisper.
- George has TWO laptops and may run meetings on either, sometimes only one: an
  Apple Silicon M4 Mac AND a Windows laptop with an RTX 5070 (~8 GB VRAM, 32 GB RAM).
  So the recorder + transcription must be cross-platform.
- mlx-whisper (briefly chosen for the M4) is Apple-Silicon-only -> fails Windows.
  faster-whisper runs on both (CUDA on the 5070, CPU on the Mac).

## Decision
1. **Dedicated meeting bot** — a SEPARATE Discord app + token, **one portable Python
   codebase** that runs on whichever laptop George has that day (Mac or Windows).
   Online only during meetings. Records + (async) transcribes locally. The existing
   ops bot (Aboyeur on EC2) stays 24/7 for text/Notion/reminders.
2. **Transcription is async/decoupled** — /record stop saves per-user audio +
   metadata (guaranteed), returns instantly; a separate pass transcribes later,
   retry-safe, never endangering the recording. Record + transcribe co-located on
   the same laptop -> no file transfer.
3. **Engine = faster-whisper, large-v3, full precision (fp16)** — cross-platform.
   Auto-selects CUDA when an NVIDIA GPU is present (Windows RTX 5070 -> fast, fp16
   ~5 GB VRAM fits), else CPU (Mac M4 -> slower but full quality; acceptable since
   async + quality>speed). NOT quantized.
4. **Local, not cloud** — keeps teammate audio on the laptop (privacy + clean
   consent), accepting that cloud ASR might edge raw accuracy.

## Alternatives Considered
- Record on EC2 / resize EC2 — fails RAM/disk/GPU. Rejected.
- mlx-whisper — GPU-fast on the M4, but Apple-Silicon-ONLY -> fails the Windows
  laptop. Dropped once cross-platform (two laptops) became the requirement.
- whisper.cpp — cross-platform + fast, but C++ build overhead vs faster-whisper's
  pip install. Set aside.
- Cloud gpt-4o-transcribe — higher accuracy ceiling but sends teammate audio off-box
  + per-minute cost. Rejected on privacy; may A/B later.
- Single bot / same token on Mac — can't; one token can't be in two places, and the
  ops bot must stay on EC2. Hence a second app/token.

## Consequences
- A 2nd Discord app/token to create + manage; George starts the meeting bot before
  meetings on whichever laptop he has. Portable codebase, deps installed on both.
- Build deps (both OSes): py-cord[voice] (PyNaCl), ffmpeg, opus, faster-whisper +
  large-v3 weights. Windows adds a CUDA path.
- **Blackwell caveat**: RTX 50-series is new — faster-whisper's CTranslate2 backend
  needs a recent CUDA 12.x + cuDNN 9 build for it. Likely the latest CTranslate2.
  Handle at build; can be finicky on first CUDA setup.
- Quality ceiling capped at local large-v3 by choice; revisit only if insufficient.
- GPU/CPU open question resolved: CUDA on the Windows 5070 (full fp16), CPU on Mac.
- Speed varies by host (fast on 5070, slow on M4 CPU); decoupled async absorbs this.

## Still open (pinned)
- Storage/delivery of big audio files (Discord upload cap) — DEFERRED by George.
- Consent policy + wording (D3), transcript format (D6) — decide at build time.
