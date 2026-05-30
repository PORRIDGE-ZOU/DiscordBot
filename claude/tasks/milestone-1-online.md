# Milestone 1: bot online + /ping

Smallest real bot. Proves token -> gateway -> intents -> slash command -> response.

## Done
- requirements.txt (py-cord, python-dotenv)
- .env.example (DISCORD_TOKEN, optional DISCORD_GUILD_ID)
- .gitignore (.env, venv, recordings/, transcripts/)
- bot.py (intents, /ping slash command, on_ready)
- README.md (portal setup, intents, scopes, run instructions)

## George's actions (prereqs to run)
- [x] App created + bot invited to server
- [ ] Token in .env
- [ ] Message Content + Server Members intents enabled in portal
- [ ] (optional) DISCORD_GUILD_ID set for instant slash registration

## Run (George runs these — not Claude)
- python3 -m venv venv && source venv/bin/activate
- pip install -r requirements.txt
- python bot.py
- test /ping in server

## Next milestone
- Scheduled messaging (feature 1). Need George's spec: which channels, what
  cadence, what wording, who gets DMs.
