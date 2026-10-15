import base64
import itertools
import json
import os
import re
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
#   GEMINI_DEEP_MODEL model for the second, thinking pass on questions (default below)
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_DEEP_MODEL = "gemini-2.5-flash"  # 2.0-flash can't think, so the deep pass needs a 2.5+ model

# per-call time limits: a late tip is a useless tip, so quick calls give up fast
QUICK_TIMEOUT_S = 4       # one-shot calls (suggest / tip detail)
ANSWER_TIMEOUT_S = 6      # first answer to a question
DEEP_TIMEOUT_S = 15       # second pass that thinks before answering
DEEP_THINKING_BUDGET = 1024


def _load_system_prompt() -> str:
    with open(os.path.join(_PROMPTS_DIR, "context.txt")) as f:
        return f.read().strip()


# ── Errors ────────────────────────────────────────────────────────────────────

class CoachError(Exception):
    """A coach call failed. str() is short enough to show on the overlay.
    kind: timeout | quota | auth | unavailable | unreachable | no_game | bad_reply | error"""
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _classify(e: Exception, backend_name: str, timeout_s: float) -> CoachError:
    """Map SDK / HTTP / parse exceptions from any backend onto a CoachError."""
    if isinstance(e, CoachError):
        return e
    # match by class name so this works for httpx (google-genai) and requests (lmstudio) alike
    names = {c.__name__ for c in type(e).__mro__}
    if any("Timeout" in n for n in names):
        return CoachError("timeout", f"Coach took too long (>{timeout_s:.0f}s)")
    if names & {"ConnectError", "ConnectionError"}:
        return CoachError("unreachable", f"Can't reach the coach model ({backend_name})")
    if isinstance(e, json.JSONDecodeError):
        return CoachError("bad_reply", "Coach sent an unreadable reply")
    code = getattr(e, "code", None)  # google.genai.errors.APIError
    if code is None and getattr(e, "response", None) is not None:
        code = getattr(e.response, "status_code", None)  # requests.HTTPError
    if code == 429 or "quota" in str(e).lower():
        return CoachError("quota", "Rate-limited on every API key — try again in a minute")
    if code in (401, 403):
        return CoachError("auth", "API key rejected — check your .env")
    if isinstance(code, int) and code >= 500:
        return CoachError("unavailable", "Coach model is overloaded — try again")
    msg = getattr(e, "message", None) or str(e)
    return CoachError("error", msg if len(msg) <= 120 else msg[:117] + "…")


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

    def __init__(self, api_keys: list[str], model: str = DEFAULT_GEMINI_MODEL,
                 deep_model: str = DEFAULT_DEEP_MODEL):
        if not api_keys:
            raise RuntimeError("COACH_BACKEND=gemini but no GEMINI_API_KEY* is set")
        from google import genai           # deferred so the lmstudio backend
        from google.genai import types     # doesn't need google-genai installed
        self._genai, self._types = genai, types
        self._keys = itertools.cycle(api_keys)
        self.n_keys = len(api_keys)
        self.model, self.deep_model = model, deep_model
        self.name = f"gemini:{model} ({len(api_keys)} key{'s' if len(api_keys) > 1 else ''})"
        # Quick calls want no thinking: it's slow and counts against max_output_tokens (truncating
        # the JSON). Some models refuse budget 0 (pro, gemini 3) → step down to the smallest budget
        # they take, then to the model's default. Latched per model on the first refusal.
        self._quick_budgets = {model: [0, 128, None]}
        self.can_think = True  # deep pass available; latched off if the deep model refuses
        self.rotate()

    def rotate(self):
        """Switch to the next API key."""
        self._client = self._genai.Client(api_key=next(self._keys))

    def generate(self, system: str, history: list[tuple[str, str]], prompt: str,
                 image: bytes | None, max_tokens: int, timeout_s: float, deep: bool = False) -> str:
        t = self._types
        contents = [t.Content(role="model" if role == "assistant" else "user", parts=[t.Part(text=text)])
                    for role, text in history]
        parts = [t.Part(text=prompt)]
        if image:
            parts.append(t.Part.from_bytes(data=image, mime_type="image/jpeg"))
        contents.append(t.Content(role="user", parts=parts))
        config = dict(system_instruction=system, response_mime_type="application/json",
                      http_options=t.HttpOptions(timeout=int(timeout_s * 1000)), temperature=0.4)
        if deep:
            try:  # thinking tokens count against the output budget → add them on top
                return self._send(self.deep_model, contents, dict(config, max_output_tokens=DEEP_THINKING_BUDGET + max_tokens),
                                  t.ThinkingConfig(thinking_budget=DEEP_THINKING_BUDGET))
            except Exception as e:
                if _refuses_thinking(e):
                    self.can_think = False
                    raise CoachError("error", f"{self.deep_model} can't think — set GEMINI_DEEP_MODEL") from e
                raise
        budgets = self._quick_budgets.setdefault(self.model, [0, 128, None])
        while True:
            budget = budgets[0]
            # floor: room to finish if the model thinks anyway
            cfg = dict(config, max_output_tokens=max(max_tokens, 1024) + (budget or 0))
            try:
                return self._send(self.model, contents, cfg,
                                  None if budget is None else t.ThinkingConfig(thinking_budget=budget))
            except Exception as e:
                if budget is None or not _refuses_thinking(e):
                    raise
                print(f"[coach] {self.model} refused thinking budget {budget}, trying {budgets[1]}")
                budgets.pop(0)

    def _send(self, model: str, contents, config: dict, thinking=None) -> str:
        t = self._types
        response = self._client.models.generate_content(
            model=model, contents=contents,
            config=t.GenerateContentConfig(**config, thinking_config=thinking))
        if not response.text:  # .text skips thought parts, so a reply that only thought is empty too
            cand = response.candidates[0] if response.candidates else None
            feedback = response.prompt_feedback
            reason = (cand and cand.finish_reason) or (feedback and feedback.block_reason) or "no text"
            raise CoachError("bad_reply", f"Coach sent no answer ({getattr(reason, 'name', reason)})")
        return response.text


def _refuses_thinking(e: Exception) -> bool:
    """A 400 complaining about the thinking config (budget out of range / unsupported)."""
    return getattr(e, "code", None) == 400 and "thinking" in str(e).lower()


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
        self.n_keys = 1
        self.can_think = False  # no thinking switch over the OpenAI API → no deep pass

    def rotate(self):
        pass  # single endpoint, nothing to rotate

    def generate(self, system: str, history: list[tuple[str, str]], prompt: str,
                 image: bytes | None, max_tokens: int, timeout_s: float, deep: bool = False) -> str:
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
        resp = requests.post(self._endpoint, json=body, headers=self._headers, timeout=timeout_s)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    """Parse a JSON reply, tolerating ```json fences / chatter / <think> blocks around it
    (local models don't always honour "JSON only")."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
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
        return LoLCoach(GeminiBackend(keys, os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
                                      os.environ.get("GEMINI_DEEP_MODEL") or DEFAULT_DEEP_MODEL))
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

    @property
    def can_think(self) -> bool:
        """Whether deep=True calls can work (the backend has a thinking model)."""
        return self._backend.can_think

    def new_session(self):
        """New game: forget this game's chat (keeps the last-game summary from memory)."""
        self._history, self.last_game = load_memory()

    def _call(self, question: str | None, schema_key: str,
              context: dict | None = None, image: bytes | None = None,
              one_shot: bool = False, state: dict | None = None, max_tokens: int | None = None,
              timeout_s: float = ANSWER_TIMEOUT_S, deep: bool = False) -> dict:
        """Build prompt, send to the backend, parse and return JSON."""
        schema = SCHEMAS[schema_key]
        if state is None:
            try:
                state = compress_game_state()
            except Exception as e:
                raise CoachError("no_game", "No live game data — is a game running?") from e

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
                                      prompt, image, max_tokens or (150 if one_shot else 300), timeout_s, deep)
        result = _parse_json(text)
        if not isinstance(result, dict):
            raise CoachError("bad_reply", "Coach sent an unreadable reply")
        if not one_shot:
            self._history += [("user", prompt), ("assistant", text)]
        return result

    def get_advice(self, question: str = None, schema_key: str = "situation",
                   context: dict = None, image: bytes = None, one_shot: bool = False,
                   state: dict = None, max_tokens: int = None, timeout_s: float = None,
                   deep: bool = False) -> dict:
        """
        Fetch live state and return coaching JSON. Never raises: on failure returns
        {"error": kind, "action": short message for the overlay} (kinds: see CoachError).

        Args:
            question:   optional free-text player question → uses "question" schema
            schema_key: "situation" | "question" | "suggest" | "event" | "post_game"
            context:    optional extra facts (e.g. recent deaths/objectives) sent with the prompt
            image:      optional JPEG screenshot bytes for a vision call
            one_shot:   send without chat history (fast, for quick suggestions)
            state:      game state to send instead of the live one (e.g. champ select — the
                        Live Client API doesn't exist yet)
            max_tokens: reply budget override (default 150 one-shot / 300)
            timeout_s:  give up after this long (default QUICK_TIMEOUT_S one-shot / ANSWER_TIMEOUT_S,
                        DEEP_TIMEOUT_S when deep)
            deep:       let the model think first (slower, better) — only if can_think
        """
        if question and schema_key == "situation":
            schema_key = "question"
        if timeout_s is None:
            timeout_s = DEEP_TIMEOUT_S if deep else QUICK_TIMEOUT_S if one_shot else ANSWER_TIMEOUT_S

        rotations, retried = 0, False
        while True:
            try:
                return self._call(question, schema_key, context, image, one_shot, state, max_tokens,
                                  timeout_s, deep)
            except Exception as e:
                err = _classify(e, self.name, timeout_s)
                print(f"[coach] {schema_key}{' (deep)' if deep else ''} failed [{err.kind}]: {e}")
                if err.kind == "quota" and rotations < self._backend.n_keys - 1:
                    rotations += 1
                    self._backend.rotate()
                    continue
                # one retry for a transient 5xx; timeouts aren't retried (that would double the wait)
                if err.kind == "unavailable" and not retried:
                    retried = True
                    continue
                return {"error": err.kind, "action": str(err)}

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
