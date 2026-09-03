"""Interactive two-part jokes: the bot asks, you guess, the bot pays it off.

The jokes come from `jokes.json`, a fixed pack shipped with the bot — 100 food and
100 general, weighted towards food. Telling a joke costs NO API call and is
instant: no waiting on a model to think one up, and it still works when the API key
is missing or OpenAI is down.

The pack is a plain JSON file precisely so it can be curated. A model asked for a
joke on demand gives you its median joke forever; a file lets you delete the ones
that don't land, and they stay deleted.

The only thing still generated live is the one-line reaction to YOUR guess — that
part can't be canned, because reacting to what someone actually typed is the whole
point of the interaction. It degrades to silence if the call fails.

Pending jokes live in a plain dict — deliberately NOT in botstate.db. A restart
forgets every joke in flight, which is the intended behaviour: a stale punchline
from before a deploy isn't worth persisting, and /joke-reply says plainly when
there's nothing waiting.

Like timeoff.py, this module owns its calls to OpenAI and knows nothing about
Discord. The client is synchronous, so async callers use asyncio.to_thread.
"""

import json
import os
import random

from openai import OpenAI

# discord_user_id -> {"setup": str, "punchline": str}
# Module-level, so it dies with the process. One joke in flight per person.
_pending = {}

# Shuffled decks, one per pack, dealt from until empty then reshuffled. Lives in
# memory alongside _pending, so a restart reshuffles — which is fine.
_decks = {}


_client = None


def _get_client():
    """One lazily-built client, so importing this module never needs the key."""
    global _client
    if _client is None:
        # KeyError here = OPENAI_API_KEY missing from .env
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _model():
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


_JOKES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jokes.json")

# Chance a joke is drawn from the food pack rather than the general one. The bot is
# named after a kitchen role and lives in a restaurant-sim team's server, so food is
# the house style — tune this one number to change the mix.
FOOD_WEIGHT = 0.75

_packs = None


def _load_packs():
    """Read jokes.json once. Missing or malformed = a clear error, not a silent
    empty bot."""
    global _packs
    if _packs is None:
        with open(_JOKES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        packs = {
            name: [j for j in data.get(name, []) if j.get("setup") and j.get("punchline")]
            for name in ("food", "general")
        }
        if not packs["food"] and not packs["general"]:
            raise ValueError(f"{_JOKES_PATH} has no usable jokes")
        _packs = packs
    return _packs


def _draw():
    """Pick a joke, preferring ones not told yet this run.

    Shuffled decks rather than independent random picks: with 200 jokes and plain
    random choice you'd hit a repeat surprisingly early (the birthday problem —
    about a 50/50 chance within ~17 jokes). Dealing from a shuffled deck means no
    repeat until the deck is exhausted.
    """
    packs = _load_packs()
    name = "food" if random.random() < FOOD_WEIGHT else "general"
    if not packs[name]:  # a pack emptied by editing jokes.json — use the other
        name = "general" if name == "food" else "food"

    deck = _decks.get(name)
    if not deck:
        deck = list(packs[name])
        random.shuffle(deck)
        _decks[name] = deck
    return deck.pop()


_REACTION_PROMPT = """\
You are Sous Chef, a Discord bot, running a joke on a student game-dev team's server.

You told someone a joke setup and they guessed the punchline. Write ONE short, warm,
playful sentence reacting to THEIR guess — at most 25 words.

- If they got it right (or close), say so with delight.
- If they're wrong but funny, admit theirs is better.
- If they're wrong and random, be amused, never mean.
- If they clearly didn't try ("idk", "no"), tease gently.

CRITICAL: do NOT state or hint at the real punchline. It is shown immediately after
your sentence, and repeating it ruins the beat. React only. No quotation marks around
your whole reply, no preamble.\
"""


def new_joke(discord_id):
    """Take a joke from the pack, remember the punchline, return the setup.

    No network call — this is a dict lookup. Replaces any joke this person already
    had pending; running /joke twice just means you'd rather have a different one.
    """
    joke = _draw()
    _pending[discord_id] = {"setup": joke["setup"], "punchline": joke["punchline"]}
    return joke["setup"]


def has_pending(discord_id):
    return discord_id in _pending


def answer(discord_id, guess):
    """Reveal the punchline for this person's pending joke.

    Returns (setup, guess, reaction, punchline), or None if they have nothing
    pending. The joke is consumed either way. Blocking; call via to_thread.
    """
    joke = _pending.pop(discord_id, None)
    if joke is None:
        return None

    # The reaction is the garnish. If it fails, the punchline still lands — so a
    # flaky second call must never cost the user their joke.
    reaction = ""
    try:
        response = _get_client().chat.completions.create(
            model=_model(),
            temperature=1.0,
            max_tokens=80,
            messages=[
                {"role": "system", "content": _REACTION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Setup: {joke['setup']}\n"
                        f"Real punchline (do not reveal): {joke['punchline']}\n"
                        f"Their guess: {guess}"
                    ),
                },
            ],
        )
        reaction = (response.choices[0].message.content or "").strip()
    except Exception:
        reaction = ""

    return joke["setup"], guess, reaction, joke["punchline"]
