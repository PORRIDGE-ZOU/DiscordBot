# Deploy via GitHub pull (replaces rsync)

**Date**: 2026-05-30
**Decided by**: George
**Status**: Active

## Context
Initial EC2 deploys used rsync from the Mac. George wanted Git-based deploys (push
from Mac, pull on server) — cleaner history, and the local repo already had a remote.

## Decision
Deploy through GitHub. Mac: `git push origin main`. EC2: `./deploy.sh` (git pull →
pip install → systemctl restart qlpbot). Server authenticates with a fine-grained
read-only PAT stored via git credential helper.

## Alternatives Considered
- **rsync** (prior method) — works but can clobber untracked server state and has no
  version history. Superseded.
- **SSH deploy key** (read-only, repo-scoped) — recommended as most secure; George
  chose HTTPS PAT for simplicity (already had a token).

## Consequences
- `git pull` never touches untracked files → `.env` and `jobs.sqlite` (live
  reminders) are safe by design; the rsync `--exclude jobs.sqlite` concern is gone.
- PAT sits in `~/.git-credentials` (plaintext, 600) on the server — rotate if box
  exposed. Use a fine-grained, read-only, this-repo-only, expiring token.
- `.env` must never be committed; verify it's not in history before pushing.
- `deploy.sh` lives in the repo root; `chmod +x` once on the server.
- Don't mix rsync and git going forward.
