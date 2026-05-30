# Deploying + running the bot on AWS EC2

How the bot is hosted so it stays online when your laptop is off, and how to
operate it day to day. The bot runs on an existing **Amazon Linux 2023** EC2
instance (a `t3.micro`, shared with an unrelated Steam-scraper job), kept alive by
**systemd**.

This is dev/ops documentation. If you just want to *use* the bot in Discord, see
`using-the-bot.md`.

## The shape of it

- The bot is a long-lived process started by a **systemd service** (`qlpbot`).
  systemd starts it on boot, restarts it if it crashes, and keeps it running after
  you disconnect SSH.
- It coexists with the Steam scraper: its own directory (`~/DiscordBot`), its own
  virtualenv, its own service. The only shared resource is the instance's 1 GB RAM,
  cushioned by a 2 GB swap file.
- The bot only makes **outbound** connections (to Discord + Notion), so no inbound
  security-group rules are needed beyond SSH.

> **One instance only.** A Discord token can run in exactly one place at a time.
> Running `python bot.py` on your Mac while the EC2 service is up creates a second
> gateway session and the bot double-replies. Keep the bot **only** on EC2; use your
> Mac solely to edit code and re-sync.

## Connection details

- **Host**: `ec2-user@3.151.10.101` (Public IPv4; check the EC2 console if it changes
  after a stop/start — a plain instance gets a new IP on stop/start unless it has an
  Elastic IP).
- **Key**: `~/Desktop/Jobs/TGC/steam_scraper/steam_key.pem` (the key pair the
  instance was launched with — the only key that can log in).
- **OS**: Amazon Linux 2023 → user `ec2-user`, package manager `dnf`, Python 3.11.

```bash
ssh -i /Users/porridge/Desktop/Jobs/TGC/steam_scraper/steam_key.pem ec2-user@3.151.10.101
```

## First-time setup (already done — recorded for rebuilds)

1. **Swap** (2 GB) — protects the bot from OOM during the scraper's daily spike:
   ```bash
   sudo dd if=/dev/zero of=/swapfile bs=128M count=16
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
   ```
2. **Runtime**:
   ```bash
   sudo dnf -y install python3.11 python3.11-pip git
   ```
3. **Code** — from your Mac (no `sudo` needed):
   ```bash
   rsync -av -e "ssh -i ~/Desktop/Jobs/TGC/steam_scraper/steam_key.pem" \
     --exclude venv --exclude .env --exclude .git --exclude __pycache__ --exclude '.DS_Store' \
     ~/Desktop/usccourse/DiscordBot/ ec2-user@3.151.10.101:/home/ec2-user/DiscordBot/
   ```
   (Paste as ONE line — backslash continuations break if blank lines sneak in.)
4. **Secrets + venv** — on the server:
   ```bash
   cd ~/DiscordBot
   nano .env        # DISCORD_TOKEN, DISCORD_GUILD_ID, NOTION_TOKEN, NOTION_TASKS_DB_ID
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   `.env` is created on the server and never copied around (rsync excludes it).
5. **systemd service** — `/etc/systemd/system/qlpbot.service`:
   ```ini
   [Unit]
   Description=Quarter Life Pounder Discord bot
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=ec2-user
   WorkingDirectory=/home/ec2-user/DiscordBot
   ExecStart=/home/ec2-user/DiscordBot/venv/bin/python /home/ec2-user/DiscordBot/bot.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now qlpbot
   ```

`dotenv` loads `.env` from `WorkingDirectory`, so no secrets live in the unit file.

## Day-to-day operations

| Goal | Command |
| --- | --- |
| Is it running? | `sudo systemctl status qlpbot` |
| Live logs | `journalctl -u qlpbot -f` |
| Recent logs | `journalctl -u qlpbot -n 50 --no-pager` |
| Restart (after a code update) | `sudo systemctl restart qlpbot` |
| Stop / start | `sudo systemctl stop qlpbot` / `start` |
| RAM + swap | `free -h` |
| Disk | `df -h /` |

### Pushing a code change
1. On your Mac, re-run the **rsync** from step 3 (it only sends changed files).
2. SSH in. If `requirements.txt` changed:
   `cd ~/DiscordBot && source venv/bin/activate && pip install -r requirements.txt`.
3. `sudo systemctl restart qlpbot`.
4. `journalctl -u qlpbot -n 20 --no-pager` to confirm a clean restart.

Remember: any new or changed **slash command** only registers on (re)start — the
restart in step 3 covers it.

## Things to watch

- **Disk.** The scraper "stores everything," and root is only 8 GB (was ~47% used at
  setup). When `df -h /` climbs toward full, both the bot and the scraper break
  (can't write). Mitigate later by expanding the EBS volume or pruning scraper data.
- **RAM during the daily scrape.** With 1 GB + 2 GB swap, a scrape spike should swap
  rather than kill the bot, and `Restart=always` recovers it if it does die. If
  `journalctl` shows the bot restarting around the scrape time, that's the signal to
  resize the instance (`t3.small`, 2 GB) or move the bot to its own free box (Oracle).
- **Public IP.** A stop/start of the instance changes the IP unless an Elastic IP is
  attached. If the IP changes, update your `ssh`/`rsync` host.

## If you ever rebuild from scratch

Follow "First-time setup" top to bottom on a fresh Amazon Linux 2023 instance. The
only inputs you need are the four `.env` values and this repo.
