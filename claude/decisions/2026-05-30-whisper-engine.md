# Transcription Engine: faster-whisper large-v3 (local)

**Date**: 2026-05-30
**Decided by**: Claude recommendation, accepted by George
**Status**: Superseded (engine) by 2026-05-30-meeting-bot-and-engine.md — switched
faster-whisper -> mlx-whisper for the M4 Mac (same large-v3 model + quality; better
speed on Apple Silicon). The "local large-v3, quality over speed, decoupled" intent
still holds.

## Context
The bot must transcribe team meetings with faithful, dynamic English/Chinese
handling (incl. code-switching). George's selection criterion was explicit:
**best transcription quality, not speed.** An earlier quick pick (OpenAI Whisper
API) was made before the quality-vs-speed framing; this decision supersedes it.

## Decision
Use **faster-whisper** running the **large-v3** model locally, as a separate
offline pass over saved per-user audio. Language is auto-detected per utterance
chunk to give dynamic EN/ZH switching across utterances.

## Alternatives Considered
- **OpenAI Whisper API (`whisper-1`)** — convenient, no local compute, but the
  served model is large-v2 (older, weaker on Chinese than v3), gives one dominant
  language per request rather than per-segment control, and sends teammates'
  audio to the cloud (consent weight). Set aside.
- **OpenAI `gpt-4o-transcribe`** — may edge large-v3 on raw WER, but is a black
  box with no per-segment language control, sends audio off-machine, and costs
  per minute. Set aside on control + privacy grounds, not quality alone.

## Consequences
- Local compute required. **Open question now live: GPU vs CPU**, which sets the
  realistic model size and per-meeting transcription time (CPU large-v3 ≈ 30+ min
  for an hour of audio; GPU ≈ minutes). Pending George's confirmation of available
  hardware.
- Privacy benefit: meeting audio never leaves George's machine.
- Matches the AGENTS.md architecture baseline (recording decoupled from
  transcription; per-chunk language detection).
