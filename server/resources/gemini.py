import base64
import itertools
import json
import os
import requests
import urllib3

from dotenv import load_dotenv

'''
from ollama import chat

response = chat(
    model='gemma4',
    messages=[{'role': 'user', 'content': 'Hello!'}],
)
print(response.message.content)

'''

load_dotenv()

from server.resources.riot import (
    get_active_player,
    get_player_scores,
    get_game_stats,
)
from server.resources.prompts.schemas import SCHEMAS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Config ────────────────────────────────────────────────────────────────────

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_MEMORY_FILE = os.path.join(os.path.dirname(__file__), "coach_memory.json")

# Backend + model are chosen by env vars (see .env.example):
#   COACH_BACKEND     "gemini" (default) | "lmstudio"
#   GEMINI_MODEL      e.g. gemini-2.0-flash (default) — fast/cheap; bigger models are slower
#   GEMINI_API_KEY*   every var starting with GEMINI_API_KEY is a key (commas split
#                     several keys in one var); keys rotate on 429 / quota errors
#   LMSTUDIO_URL      base URL of an OpenAI-compatible server, e.g. https://lm.example.com
#   LMSTUDIO_MODEL    model id as LM Studio lists it (empty = whatever is loaded)
#   LMSTUDIO_API_KEY  optional bearer token, e.g. for an auth proxy in front of LM Studio
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
REQUEST_TIMEOUT_S = 30


def _load_system_prompt() -> str:
    with open(os.path.join(_PROMPTS_DIR, "context.txt")) as f:
        return f.read().strip()


# ── State compression ─────────────────────────────────────────────────────────

def compress_game_state() -> dict:
    """
    Pull live data from the Riot API and strip it to coaching-relevant fields.
    Keeps per-turn token cost to ~150 bytes vs ~4 KB raw.
    """
    active  = get_active_player()
    game    = get_game_stats()
    riot_id = active.get("riotId", "")
    scores  = get_player_scores(riot_id) if riot_id else {}
    cs      = active["championStats"]

    return {
        "t":    round(game.get("gameTime", 0)),
        "clock": f"{int(game.get('gameTime', 0)) // 60}:{int(game.get('gameTime', 0)) % 60:02d}",
        "mode": game.get("gameMode", ""),
        "hp":   round(cs.get("currentHealth", 0)),
        "mhp":  round(cs.get("maxHealth", 1)),
        "mp":   round(cs.get("resourceValue", 0)),
        "mmp":  round(cs.get("resourceMax", 1)),
        "g":    round(active.get("currentGold", 0)),
        "lvl":  active.get("level", 1),
        "k":    scores.get("kills", 0),
        "d":    scores.get("deaths", 0),
        "a":    scores.get("assists", 0),
        "cs":   scores.get("creepScore", 0),
        "ad":   round(cs.get("attackDamage", 0)),
        "ap":   round(cs.get("abilityPower", 0)),
    }


# ── Session memory ────────────────────────────────────────────────────────────

def load_memory() -> tuple[list[tuple[str, str]], dict]:
    """
    Returns (prior_context_messages, last_game_summary).
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
        ("user",      f"Summary of my last game: {json.dumps(last_game)}"),
        ("assistant", "Got it. I'll keep that in mind for this session."),
    ]
    return prior_context, last_game


def save_memory(game_summary: dict):
    """Persist a compact game summary for the next session."""
    with open(_MEMORY_FILE, "w") as f:
        json.dump({"last_game": game_summary}, f, indent=2)


# ── Backends ──────────────────────────────────────────────────────────────────
# A backend turns (system prompt, history, prompt, optional image) into reply
# text. History is [(role, text)] with role "user" | "assistant".

class GeminiBackend:
    """Google Gemini via google-genai. Rotates through API keys on quota errors."""

    def __init__(self, api_keys: list[str], model: str = DEFAULT_GEMINI_MODEL):
        if not api_keys:
            raise RuntimeError("COACH_BACKEND=gemini but no GEMINI_API_KEY* is set")
        from google import genai           # deferred so the lmstudio backend
        from google.genai import types     # doesn't need google-genai installed
        self._genai, self._types = genai, types
        self._keys = itertools.cycle(api_keys)
        self.model = model
        self.name = f"gemini:{model} ({len(api_keys)} key{'s' if len(api_keys) > 1 else ''})"
        # thinking models (2.5+, *-latest) count thinking against max_output_tokens and
        # truncate the JSON — ask for no thinking; dropped if the model refuses
        self._thinking_off = True
        self.rotate()

    def rotate(self):
        """Switch to the next API key."""
        self._client = self._genai.Client(api_key=next(self._keys))

    def generate(self, system: str, history: list[tuple[str, str]], prompt: str,
                 image: bytes | None, max_tokens: int) -> str:
        t = self._types
        contents = [t.Content(role="model" if role == "assistant" else "user", parts=[t.Part(text=text)])
                    for role, text in history]
        parts = [t.Part(text=prompt)]
        if image:
            parts.append(t.Part.from_bytes(data=image, mime_type="image/jpeg"))
        contents.append(t.Content(role="user", parts=parts))
        config = dict(system_instruction=system, response_mime_type="application/json",
                      # floor: room to finish if the model thinks anyway
                      max_output_tokens=max(max_tokens, 1024), temperature=0.4)
        if self._thinking_off:
            try:
                return self._send(contents, config, t.ThinkingConfig(thinking_budget=0))
            except Exception as e:
                if "thinking" not in str(e).lower():
                    raise
                self._thinking_off = False  # e.g. pro / gemini 3 models can't turn it off
        return self._send(contents, config)

    def _send(self, contents, config: dict, thinking=None) -> str:
        t = self._types
        response = self._client.models.generate_content(
            model=self.model, contents=contents,
            config=t.GenerateContentConfig(**config, thinking_config=thinking))
        if not response.text:
            raise RuntimeError(f"empty reply from {self.model}")
        return response.text


class LMStudioBackend:
    """OpenAI-compatible chat completions — e.g. LM Studio serving Gemma on a
    personal server, reached directly or through a proxy."""

    def __init__(self, url: str, model: str = "", api_key: str | None = None):
        if not url:
            raise RuntimeError("COACH_BACKEND=lmstudio but LMSTUDIO_URL is not set")
        url = url.rstrip("/")
        self._endpoint = url + ("/chat/completions" if url.endswith("/v1") else "/v1/chat/completions")
        self.model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.name = f"lmstudio:{model or '(loaded model)'} @ {self._endpoint}"

    def rotate(self):
        pass  # single endpoint, nothing to rotate

    def generate(self, system: str, history: list[tuple[str, str]], prompt: str,
                 image: bytes | None, max_tokens: int) -> str:
        user = prompt
        if image:
            data_url = "data:image/jpeg;base64," + base64.b64encode(image).decode()
            user = [{"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}]
        messages = ([{"role": "system", "content": system}]
                    + [{"role": role, "content": text} for role, text in history]
                    + [{"role": "user", "content": user}])
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.4}
        if self.model:
            body["model"] = self.model
        resp = requests.post(self._endpoint, json=body, headers=self._headers, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    """Parse a JSON reply, tolerating ```json fences / chatter around it
    (local models don't always honour "JSON only")."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def coach_from_env() -> "LoLCoach":
    """Build a LoLCoach from env vars (COACH_BACKEND etc. — see Config above)."""
    backend = os.environ.get("COACH_BACKEND", "gemini").strip().lower()
    if backend == "gemini":
        keys = [k.strip()
                for name, value in sorted(os.environ.items()) if name.startswith("GEMINI_API_KEY")
                for k in value.split(",") if k.strip()]
        return LoLCoach(GeminiBackend(keys, os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL))
    if backend == "lmstudio":
        return LoLCoach(LMStudioBackend(os.environ.get("LMSTUDIO_URL", ""),
                                        os.environ.get("LMSTUDIO_MODEL", ""),
                                        os.environ.get("LMSTUDIO_API_KEY") or None))
    raise RuntimeError(f"unknown COACH_BACKEND={backend!r} (use 'gemini' or 'lmstudio')")


# ── Coach ─────────────────────────────────────────────────────────────────────

class LoLCoach:
    def __init__(self, backend):
        self._backend = backend
        self.name     = backend.name
        self._system  = _load_system_prompt()

        # conversation so far, sent with every non-one-shot call. Text only:
        # screenshots go with their own request but aren't replayed later.
        self._history, self.last_game = load_memory()

    def new_session(self):
        """New game: forget this game's chat (keeps the last-game summary from memory)."""
        self._history, self.last_game = load_memory()

    def _call(self, question: str | None, schema_key: str,
              context: dict | None = None, image: bytes | None = None,
              one_shot: bool = False, state: dict | None = None, max_tokens: int | None = None) -> dict:
        """Build prompt, send to the backend, parse and return JSON."""
        schema = SCHEMAS[schema_key]
        if state is None:
            state = compress_game_state()

        prompt = (
            f"schema:{json.dumps(schema, separators=(',',':'))} "
            f"state:{json.dumps(state, separators=(',',':'))}"
        )
        if context:
            prompt += f" context:{json.dumps(context, separators=(',',':'))}"
        if question:
            prompt += f" question:{question}"

        # one-shot: no history — smaller request, faster reply, doesn't clutter the chat
        text = self._backend.generate(self._system, [] if one_shot else self._history,
                                      prompt, image, max_tokens or (150 if one_shot else 300))
        result = _parse_json(text)
        if not one_shot:
            self._history += [("user", prompt), ("assistant", text)]
        return result

    def get_advice(self, question: str = None, schema_key: str = "situation",
                   context: dict = None, image: bytes = None, one_shot: bool = False,
                   state: dict = None, max_tokens: int = None) -> dict:
        """
        Fetch live state and return coaching JSON.

        Args:
            question:   optional free-text player question → uses "question" schema
            schema_key: "situation" | "question" | "suggest" | "event" | "post_game"
            context:    optional extra facts (e.g. recent deaths/objectives) sent with the prompt
            image:      optional JPEG screenshot bytes for a vision call
            one_shot:   send without chat history (fast, for quick suggestions)
            state:      game state to send instead of the live one (e.g. champ select — the
                        Live Client API doesn't exist yet)
            max_tokens: reply budget override (default 150 one-shot / 300)
        """
        if question and schema_key == "situation":
            schema_key = "question"

        try:
            return self._call(question, schema_key, context, image, one_shot, state, max_tokens)
        except Exception as e:
            err = str(e)
            # Rotate to next key on quota / rate-limit errors
            if "429" in err or "quota" in err.lower():
                self._backend.rotate()
                try:
                    return self._call(question, schema_key, context, image, one_shot, state, max_tokens)
                except Exception as e2:
                    err = str(e2)
            # Game client (Riot API on :2999) or model server not reachable
            if "connect" in err.lower() or "api unavailable" in err.lower():
                game_client = "2999" in err or "liveclientdata" in err
                return {"priority": "API unavailable",
                        "action": "Game client not running?" if game_client
                                  else f"Can't reach the coach model ({self.name})",
                        "warning": err}
            return {"priority": "error", "action": err, "warning": None}

    def end_session(self, result: str, champion: str, kda: str, cs: int):
        """
        Call at game end. Saves a summary for the next session and
        optionally returns post-game advice.

        Args:
            result:   "win" or "loss"
            champion: champion name
            kda:      e.g. "8/2/10"
            cs:       total creep score
        """
        summary = {"result": result, "champion": champion, "kda": kda, "cs": cs}
        save_memory(summary)
        return self.get_advice(schema_key="post_game")


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    coach = coach_from_env()
    print(f"using {coach.name}")

    print("=== live advice ===")
    print(json.dumps(coach.get_advice(), indent=2))

    print("\n=== question ===")
    print(json.dumps(coach.get_advice("should I take dragon or push mid?"), indent=2))
