"""Quarter Life Pounder Discord bot.

Milestone 1: come online and answer a /ping slash command. This is the smallest
real bot — it proves the whole chain works (token -> gateway -> intents ->
slash command -> response) before any feature is added.
"""

import os

import discord
from dotenv import load_dotenv

# Load DISCORD_TOKEN (and optional DISCORD_GUILD_ID) from the .env file into the
# process environment. Must run before we read them below.
load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]  # KeyError here = .env missing or token blank
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # optional; None if unset

# --- Intents -----------------------------------------------------------------
# Intents tell Discord which categories of events to push to us over the gateway.
# They MUST also be toggled ON in the Developer Portal (Bot page) or the gateway
# silently withholds those events — the classic "my handler runs but receives
# nothing" trap. message_content and members are *privileged* intents; we enable
# them now because later features need them (DMing members, reading messages).
# /ping itself doesn't strictly need them, but keeping code and portal in sync
# from the start avoids surprises.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Bot(intents=intents)

# A slash command registered with guild_ids appears INSTANTLY in that server.
# Registered globally (guild_ids=None) it can take up to ~1 hour to propagate.
# We use the guild scope during development if DISCORD_GUILD_ID is set.
GUILD_IDS = [int(GUILD_ID)] if GUILD_ID else None


@bot.event
async def on_ready():
    """Fires once after login + the gateway connection is established."""
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("Bot is online. Press Ctrl+C to stop.")


@bot.slash_command(name="ping", description="Check the bot is alive.", guild_ids=GUILD_IDS)
async def ping(ctx: discord.ApplicationContext):
    """Reply to /ping.

    ctx.respond() must be called within ~3 seconds of the command being invoked,
    or Discord marks the interaction as failed. A trivial reply like this is well
    inside that window; slow work (recording, transcription, Notion calls) will
    need ctx.defer() first — that comes up in later milestones.
    """
    await ctx.respond("pong 🏓")


# bot.run() opens the gateway connection and BLOCKS forever — the bot is a
# long-lived process, not a script that finishes. Closing this process (or the
# laptop) takes the bot offline.
bot.run(TOKEN)
