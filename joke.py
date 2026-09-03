"""Interactive two-part jokes: the bot asks, you guess, the bot pays it off.

The whole joke — setup AND punchline — is written in one call, and only the setup
is shown. The punchline is held in memory until you answer.

Doing it the other way round (write the setup now, improvise the punchline after
the guess) reads as more interactive but is worse: the model would be inventing an
answer to a question it had no particular answer to, so the payoff rarely lands.
Committing to the punchline up front means there really was something to guess.
What makes it feel alive is the one-line reaction to your guess, not a late-bound
punchline.

Pending jokes live in a plain dict — deliberately NOT in botstate.db. A restart
forgets every joke in flight, which is the intended behaviour: a stale punchline
from before a deploy isn't worth persisting, and /joke-reply says plainly when
there's nothing waiting.

Like timeoff.py, this module owns its calls to OpenAI and knows nothing about
Discord. The client is synchronous, so async callers use asyncio.to_thread.
"""

import json
import os

from openai import OpenAI

# discord_user_id -> {"setup": str, "punchline": str}
# Module-level, so it dies with the process. One joke in flight per person.
_pending = {}

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


_JOKE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "setup": {
            "type": "string",
            "description": "The joke's question. One sentence, under 120 characters.",
        },
        "punchline": {
            "type": "string",
            "description": "The answer to that question. Under 120 characters.",
        },
    },
    "required": ["setup", "punchline"],
}

_JOKE_PROMPT = """\
You are Sous Chef, a Discord bot for a student game-dev team building a narrative
restaurant sim. Write ONE short, silly, original joke in two parts: a setup phrased as
a QUESTION, and the punchline that answers it.

STYLE
- Mostly everyday silly jokes. Roughly one in three can riff on cooking, diners, or
  game development — never force the theme, and never explain the reference.
- Wordplay and puns are ideal. Aim for a punchline someone could *almost* guess.
- Short. Setup and punchline both under 120 characters.

RULES
- Keep it clean and workplace-safe: nothing about politics, religion, appearance, or
  anyone's identity, and never a joke about a specific real person.
- Do NOT use the knock-knock format. The setup must be a single question that can be
  answered in one go.
- The punchline must actually answer the setup. No non-sequiturs.
- Vary your material — avoid the most over-told jokes.\
"""

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
    """Write a fresh joke, remember the punchline, return the setup.

    Replaces any joke this person already had pending — running /joke twice just
    means you'd rather have a different one. Blocking (HTTP); call via to_thread.
    """
    response = _get_client().chat.completions.create(
        model=_model(),
        # High temperature on purpose: the same prompt every time, so the sampling is
        # the only thing keeping the jokes from repeating.
        temperature=1.0,
        messages=[
            {"role": "system", "content": _JOKE_PROMPT},
            {"role": "user", "content": "Tell me a joke."},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "joke", "strict": True, "schema": _JOKE_SCHEMA},
        },
    )
    data = json.loads(response.choices[0].message.content)
    setup = (data.get("setup") or "").strip()
    punchline = (data.get("punchline") or "").strip()
    if not setup or not punchline:
        raise ValueError("the joke came back missing a half")

    _pending[discord_id] = {"setup": setup, "punchline": punchline}
    return setup


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
