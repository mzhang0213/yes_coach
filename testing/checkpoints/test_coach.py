"""Headless tests for LoLCoach error / timeout / thinking handling, with fake backends
(no network, no Qt). Run from anywhere:

    python3 testing/checkpoints/test_coach.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import httpx
from google.genai import errors

from server.resources.gemini import GeminiBackend, LoLCoach, _parse_json

STATE = {"t": 600, "clock": "10:00"}


class FakeBackend:
    """Replays `replies` in order: a str is returned, an Exception is raised."""
    name = "fake"

    def __init__(self, *replies, n_keys=1):
        self.replies, self.n_keys, self.can_think = list(replies), n_keys, True
        self.calls, self.rotations = [], 0

    def rotate(self):
        self.rotations += 1

    def generate(self, system, history, prompt, image, max_tokens, timeout_s, deep=False):
        self.calls.append({"timeout_s": timeout_s, "deep": deep})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def coach(*replies, n_keys=1):
    c = LoLCoach(FakeBackend(*replies, n_keys=n_keys))
    c._history = []
    return c


def api_error(code, msg):
    return errors.APIError(code, {"error": {"code": code, "message": msg, "status": "X"}})


def test_ok_reply():
    c = coach('{"action": "Back now", "why": "350 gold", "more_thought": false}')
    r = c.get_advice("should I back?", state=STATE)
    assert r["action"] == "Back now" and "error" not in r
    assert c._backend.calls[0]["timeout_s"] == 6 and len(c._history) == 2


def test_timeout_not_retried():
    c = coach(httpx.ReadTimeout("slow"))
    r = c.get_advice("q", state=STATE, one_shot=True)
    assert r["error"] == "timeout" and "4s" in r["action"]
    assert len(c._backend.calls) == 1


def test_quota_rotates_through_every_key():
    c = coach(api_error(429, "quota"), api_error(429, "quota"), '{"action": "a", "why": "b"}', n_keys=3)
    assert c.get_advice("q", state=STATE)["action"] == "a"
    assert c._backend.rotations == 2


def test_quota_on_all_keys_gives_up():
    c = coach(api_error(429, "quota"), api_error(429, "quota"), n_keys=2)
    r = c.get_advice("q", state=STATE)
    assert r["error"] == "quota" and c._backend.rotations == 1


def test_overloaded_retried_once():
    c = coach(api_error(503, "overloaded"), api_error(503, "overloaded"))
    assert c.get_advice("q", state=STATE)["error"] == "unavailable"
    assert len(c._backend.calls) == 2


def test_auth_and_garbage_and_long_errors():
    assert coach(api_error(403, "bad key")).get_advice("q", state=STATE)["error"] == "auth"
    assert coach("not json at all").get_advice("q", state=STATE)["error"] == "bad_reply"
    assert coach("[1, 2]").get_advice("q", state=STATE)["error"] == "bad_reply"
    r = coach(ValueError("x" * 500)).get_advice("q", state=STATE)
    assert r["error"] == "error" and len(r["action"]) <= 120


def test_no_game_when_live_state_fails():
    import server.resources.gemini as g
    real, g.compress_game_state = g.compress_game_state, lambda: (_ for _ in ()).throw(ConnectionError())
    try:
        assert coach().get_advice("q")["error"] == "no_game"
    finally:
        g.compress_game_state = real


def test_deep_uses_deep_timeout():
    c = coach('{"action": "a", "why": "b"}')
    c.get_advice("q", state=STATE, deep=True)
    assert c._backend.calls[0] == {"timeout_s": 15, "deep": True}


def test_parse_strips_think_blocks():
    assert _parse_json('<think>{"x": 1} hmm</think>\n```json\n{"action": "go"}\n```') == {"action": "go"}


class FakeModels:
    """Stands in for client.models: refuses thinking budgets in `refuse`."""
    def __init__(self, refuse):
        self.refuse, self.budgets = refuse, []

    def generate_content(self, model, contents, config):
        budget = config.thinking_config.thinking_budget if config.thinking_config else None
        self.budgets.append((model, budget))
        if budget in self.refuse:
            raise api_error(400, "thinking budget is out of range")
        return type("R", (), {"text": '{"action": "a"}'})()


def gemini_with(refuse):
    b = GeminiBackend(["k"], "quick-model", "deep-model")
    b._client = type("C", (), {"models": FakeModels(refuse)})()
    b.rotate = lambda: None
    return b


def test_quick_thinking_ladder_latches():
    b = gemini_with(refuse={0})
    b.generate("s", [], "p", None, 100, 5)
    b.generate("s", [], "p", None, 100, 5)
    assert b._client.models.budgets == [("quick-model", 0), ("quick-model", 128), ("quick-model", 128)]


def test_deep_model_that_cant_think_disables_deep():
    b = gemini_with(refuse={1024})
    try:
        b.generate("s", [], "p", None, 100, 5, deep=True)
        assert False, "should raise"
    except Exception as e:
        assert "GEMINI_DEEP_MODEL" in str(e)
    assert b.can_think is False and b._client.models.budgets == [("deep-model", 1024)]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
