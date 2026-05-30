# Open Questions (blocked on George)

- **GPU vs CPU for Whisper** — sets realistic large-v3 model size + per-meeting
  transcription time. Recording is decoupled and the transcription pass is
  allowed to be slow, so CPU is viable; GPU is far faster. Need to know what
  hardware the bot will run transcription on. (Raised 2026-05-30.)
- **Hosting** — where the long-lived bot process runs to stay online (laptop for
  dev; VPS/Pi for always-on). Deferred; laptop fine to start. (Raised 2026-05-30.)
