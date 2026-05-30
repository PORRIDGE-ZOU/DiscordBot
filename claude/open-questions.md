# Open Questions (blocked on George)

- **GPU vs CPU for Whisper** — sets realistic large-v3 model size + per-meeting
  transcription time. Recording is decoupled and the transcription pass is
  allowed to be slow, so CPU is viable; GPU is far faster. Need to know what
  hardware the bot will run transcription on. (Raised 2026-05-30.)
- ~~**Hosting**~~ — RESOLVED 2026-05-30: existing AWS EC2 (Amazon Linux 2023,
  t3.micro, us-east-2), systemd service `qlpbot`, 2 GB swap, coexists with the Steam
  scraper. See decisions/2026-05-30-hosting-ec2.md + docs/howtos/deploying-on-ec2.md.

## Watch items (not blocking, surfaced by hosting)
- **EC2 disk** — 8 GB root shared with the scraper (~47% at setup). Scraper grows
  unbounded; full disk breaks both. Monitor `df -h /`; expand EBS or prune later.
- **EC2 RAM** — 1 GB shared; swap covers the daily scrape spike. If the bot restarts
  around scrape time, resize (t3.small) or isolate (Oracle free box).
