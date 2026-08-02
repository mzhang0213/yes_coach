"""Coach seam — a schema-driven JSON coaching agent.

`Coach` is the game-neutral interface the controller and data sources call.
`GeminiCoach` is the Google-Gemini implementation: it assembles a tiny inline
`schema:/state:/context:/question:` prompt, returns JSON, rotates API keys on
quota errors, prunes history, and seeds a compact last-session memory.

Game-specific behaviour — the persona and the output schemas — is injected as a
`CoachProfile`, so the same engine serves any game.
"""

import itertools
import json
import os
import threading
from dataclasses import dataclass
from typing import Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "coach_memory.json")

# Model options — swap to change quality / cost:
#   gemini-2.0-flash        fast, cheap, good for live polling  ← default
#   gemini-2.0-flash-lite   cheapest, weaker reasoning
#   gemini-1.5-pro          strong reasoning, slower, higher cost
#   gemini-2.5-pro-preview  best available, use for post_game only
MODEL = "gemini-2.0-flash"


@dataclass
class CoachProfile:
    """Per-game coaching config injected into the engine."""
    system_prompt: str          # persona / guidance (the system instruction)
    schemas: dict[str, dict]    # schema_key -> output-shape description


class Coach(Protocol):
    def get_advice(self, question: str | None = None, schema_key: str = "situation",
                   state: dict | None = None, extra: dict | None = None,
                   image=None) -> dict: ...

    def end_session(self, summary: dict) -> dict: ...


# ── Session memory ─────────────────────────────────────────────────────────

def load_memory() -> tuple[list[dict], dict]:
    """Returns (prior_context_messages, last_game_summary).

    Injects last-game facts as a single 2-message exchange rather than
    replaying full history — keeps session startup token cost near zero.
    """
    if not os.path.exists(_MEMORY_FILE):
        return [], {}

    with open(_MEMORY_FILE) as f:
        data = json.load(f)

    last_game = data.get("last_game", {})
    if not last_game:
        return [], {}

    prior_context = [
        {"role": "user",  "parts": [{"text": f"Summary of my last game: {json.dumps(last_game)}"}]},
        {"role": "model", "parts": [{"text": "Got it. I'll keep that in mind for this session."}]},
    ]
    return prior_context, last_game


def save_memory(game_summary: dict):
    """Persist a compact game summary for the next session."""
    with open(_MEMORY_FILE, "w") as f:
        json.dump({"last_game": game_summary}, f, indent=2)


# ── Coach ──────────────────────────────────────────────────────────────────

class GeminiCoach:
    def __init__(self, api_keys: list[str] | str, profile: CoachProfile,
                 model: str = MODEL):
        if isinstance(api_keys, str):
            api_keys = [api_keys]

        self._keys       = itertools.cycle(api_keys)
        self._model_name = model
        self._system     = profile.system_prompt
        self._schemas    = profile.schemas
        self._lock       = threading.Lock()  # poller + UI threads share one chat

        prior_context, self.last_game = load_memory()
        self._prior_context = prior_context
        self._init_client()

    def _init_client(self):
        """Open a client with the next key and start a fresh chat session."""
        self._client = genai.Client(api_key=next(self._keys))
        self._chat = self._client.chats.create(
            model=self._model_name,
            config=types.GenerateContentConfig(
                system_instruction=self._system,
                response_mime_type="application/json",
                max_output_tokens=300,
                temperature=0.4,
            ),
            history=self._prior_context,
        )

    def _prune_history(self, keep: int = 12):
        """Cap chat history so a long game doesn't grow context/cost unbounded.

        Preserves the seeded prior-context (last-game memory) at the front and
        keeps only the most recent `keep` messages of live exchange.
        """
        base = len(self._prior_context)
        # `_curated_history` is the SDK-internal list sent as context on each
        # send_message (see Chat.send_message: curated_history + [input]).
        hist = getattr(self._chat, "_curated_history", None)
        if hist is not None and len(hist) - base > keep:
            hist[:] = list(hist[:base]) + list(hist[-keep:])

    def _call(self, question: str | None, schema_key: str,
              state: dict | None = None, extra: dict | None = None,
              image=None) -> dict:
        """Build prompt, send to Gemini, parse and return JSON.

        Args:
            state: pre-fetched compressed state; empty dict when none applies
                   (e.g. pre-game, before any live match exists).
            extra: optional context dict (trends, map summary, checkpoint).
            image: optional PIL image (cropped minimap) for a multimodal call.
        """
        schema = self._schemas[schema_key]
        state = state or {}

        prompt = (
            f"schema:{json.dumps(schema, separators=(',',':'))} "
            f"state:{json.dumps(state, separators=(',',':'))}"
        )
        if extra:
            prompt += f" context:{json.dumps(extra, separators=(',',':'))}"
        if question:
            prompt += f" question:{question}"

        parts = [prompt] if image is None else [prompt, image]
        with self._lock:
            response = self._chat.send_message(parts)
            self._prune_history()
        return json.loads(response.text)

    def get_advice(self, question: str = None, schema_key: str = "situation",
                   state: dict | None = None, extra: dict | None = None,
                   image=None) -> dict:
        """
        Return coaching JSON for the current state.

        Args:
            question:   optional free-text player question → uses "question" schema
            schema_key: schema selecting the output shape (from the CoachProfile)
            state:      pre-fetched compressed state (build_state output)
            extra:      optional trends / map / checkpoint context
            image:      optional cropped image (multimodal)
        """
        if question and schema_key == "situation":
            schema_key = "question"

        try:
            return self._call(question, schema_key, state, extra, image)
        except Exception as e:
            err = str(e)
            # Rotate to next key on quota / rate-limit errors
            if "429" in err or "quota" in err.lower():
                self._init_client()
                try:
                    return self._call(question, schema_key, state, extra, image)
                except Exception as e2:
                    err = str(e2)
            # Game client not reachable
            if "connect" in err.lower() or "api unavailable" in err.lower():
                return {"priority": "API unavailable",
                        "action": "Game client not running?",
                        "warning": err}
            return {"priority": "error", "action": err, "warning": None}

    def end_session(self, summary: dict) -> dict:
        """Save a compact game summary for the next session and return
        post-game advice. `summary` is an opaque per-game dict."""
        save_memory(summary)
        return self.get_advice(schema_key="post_game")
