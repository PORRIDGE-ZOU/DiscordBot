# Milestone 3: Meeting recording + transcription (features 2 + 3)

PLAN — not yet approved. Recording path is sacred; decouple recording from
transcription (save audio first, always).

## The hard constraints (why this isn't just "add a command")

1. **Pycord voice sinks buffer audio in RAM until /stop.** A full meeting is held
   in memory, then written/encoded at stop. On the EC2 t3.micro (1 GB, shared with
   the scraper) this OOM-kills for any real-length meeting. => EC2 is a bad recorder.
2. **Disk.** Per-user WAV is ~10 MB/min/user (1 hr x 5 ppl ≈ 3 GB). EC2 root is 8 GB,
   ~47% used. Can't hold it. Compressed (OGG/MP3) helps but still large.
3. **Transcription can't run on EC2.** large-v3 needs real compute; t3.micro has none.
   Already decided: transcribe off-box.
4. **Discord upload limit** (~10 MB for a non-boosted bot) < a real meeting's audio.
   Posting the raw audio to a channel will often fail => need storage/offload.
5. **George's machine is an Apple Silicon M4** (Georges-Macbook-M4). faster-whisper
   (CTranslate2) has no Metal GPU support -> runs CPU-only on Mac. mlx-whisper (Apple
   MLX) or whisper.cpp use the M-series GPU and are much faster. Same large-v3 model =
   same quality; only speed differs. This reopens the engine choice on Mac.

## Recommended architecture: a dedicated "meeting bot" on the M4 Mac

Both recording AND transcription want to live on the beefy machine, and that machine
is online during meetings anyway (George runs them). So:

- **Ops bot (existing, Sous Chef on EC2)** — unchanged: text, Notion, reminders. 24/7.
- **Meeting bot (NEW, separate Discord app + token, runs on the M4 Mac)** — joins
  voice, records, saves audio, transcribes locally, posts the transcript. Online only
  during meetings (George starts it; meetings are scheduled).

Why a 2nd bot, not the same process: one token can't be in two places; the recorder
needs the Mac's RAM/GPU; co-locating record+transcribe means the audio never has to
travel between machines. EC2 stays light. Clean separation.

Tradeoff: George must start the meeting bot before a meeting. Acceptable (meetings
are scheduled + he's present). Alternative (record on EC2) fails constraints 1-3.

## Pipeline (on the Mac meeting bot)

1. `/record start` — bot joins the invoker's voice channel, posts a **consent
   notice** (CA two-party — mandatory), starts a per-user compressed sink
   (sync_start=True for track alignment).
2. `/record stop` — finalize. **Guaranteed step:** write per-user audio to
   recordings/<meeting-ts>/<user>.<ext>, ALWAYS, before anything else.
3. Transcription (separate pass, allowed to fail/retry without costing the audio):
   - per-user track -> Whisper large-v3, per-segment language auto-detect (EN/ZH).
   - merge per-user segments by timestamp -> one chronological, speaker-labeled
     transcript (speaker = Discord display name; attribution is free from per-user
     tracks, no diarization).
4. Deliver: post transcript (text/file) to a channel or DM; keep audio (offload if big).

## DECISIONS LOCKED (2026-05-30) — see decisions/2026-05-30-meeting-bot-and-engine.md
- D1 Recording host: dedicated meeting bot (2nd Discord app/token), ONE portable
  codebase run on whichever laptop George has (Mac OR Windows). Record + transcribe
  co-located that day (no transfer).
- D2 Engine: faster-whisper, large-v3, full precision (fp16), local, CROSS-PLATFORM.
  CUDA on Windows RTX 5070 (~8GB VRAM, fp16 ~5GB fits) = fast; CPU on M4 = slower but
  full quality. mlx dropped (Mac-only). Blackwell needs recent CUDA12/cuDNN9 + latest
  CTranslate2 — handle at build.
- Transcription is async/decoupled: /record stop saves audio+metadata (guaranteed,
  instant return); separate retry-safe pass transcribes later.
- Quality: local ceiling chosen over cloud (teammate-audio privacy).
- D3 storage/delivery + D4 consent wording + transcript format: still open (below).

## Open decisions still to settle

- **D1 Where recording runs**: dedicated meeting bot on M4 Mac (recommended) vs EC2
  (fails RAM/disk) vs resize EC2 (costs $, still no GPU). -> drives everything.
- **D2 Transcription engine on Mac** (revisit 2026-05-30 faster-whisper decision given
  M4): mlx-whisper (MLX, fast on M-series) vs whisper.cpp (Metal) vs faster-whisper
  (CPU on Mac, slower). All large-v3 = same quality; pick by speed/setup.
- **D3 Consent policy + wording**: presence-implies-consent vs explicit opt-in; exact
  notice text. George owns wording. Mandatory notice either way.
- **D4 Storage for audio**: Discord upload limit too small for real meetings. Options:
  hard-compress + split, local-only on Mac, or offload (S3/Google Drive) + post a link.
- **D5 Trigger**: manual /record start|stop (start here) vs auto-join scheduled meeting.
- **D6 Transcript format**: speaker labels, timestamps, per-utterance language tags?
  Chinese simplified vs traditional + punctuation (AGENTS.md caveat). George's call.
- **D7 Chinglish**: mid-sentence code-switching is imperfect in Whisper — set
  expectations, don't promise perfect intra-utterance switching.

## System deps when this is built (Mac meeting bot)
- py-cord[voice] (PyNaCl), libopus, ffmpeg.
- Whisper engine per D2 (mlx-whisper / whisper.cpp / faster-whisper) + large-v3 model.

## Sequencing proposal
1. Settle D1, D2 (+ hardware specifics: M4 RAM, meeting size).
2. Build recording first (the sacred half): /record start|stop -> guaranteed saved
   per-user audio + consent notice. Verify audio is always produced. No transcription
   yet.
3. Build transcription pass over saved audio (offline script first, then wire to bot).
4. Merge + speaker labels + delivery + storage.
Each stage approved + tested before the next. Recording proven before transcription
is layered on.
