"""LCU (LeagueClientUx) API integration — the *client* API, alive during lobby,
champ select and the rune editor (unlike the in-game Live Client API on :2999).

Auth: the running LeagueClientUx process advertises its port + a per-session
token on its command line (`--app-port`, `--remoting-auth-token`); we read those
via psutil, falling back to the `lockfile`. Requests use HTTPS basic-auth
`riot:<token>` against a self-signed cert (`verify=False`) — same posture as
riot.py.

This module is read-mostly; the one write is `apply_rune_page`, which only ever
replaces our own dedicated "Yes Coach" rune page so we never clobber the
player's saved pages.
"""

import base64
import os

import requests
import urllib3

try:
    import psutil
except ImportError:  # psutil is optional; lockfile fallback still works
    psutil = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RUNE_PAGE_NAME = "Yes Coach"

# Candidate lockfile locations (fallback when the process cmdline is unreadable).
_LOCKFILE_PATHS = [
    "/Applications/League of Legends.app/Contents/LoL/lockfile",
    os.path.expanduser(
        "~/Library/Application Support/Riot Games/League of Legends/lockfile"),
    r"C:\Riot Games\League of Legends\lockfile",
]


class LCUUnavailable(Exception):
    """Raised when the League client isn't running / can't be reached."""


# ── credential discovery ────────────────────────────────────────────────────

def _parse_cmdline_arg(cmdline: list[str], key: str) -> str | None:
    prefix = f"--{key}="
    for arg in cmdline:
        if arg and arg.startswith(prefix):
            return arg[len(prefix):]
    return None


def _creds_from_process() -> tuple[int, str] | None:
    if psutil is None:
        return None
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if "LeagueClientUx" not in (proc.info.get("name") or ""):
                continue
            cmd = proc.info.get("cmdline") or []
            port = _parse_cmdline_arg(cmd, "app-port")
            token = _parse_cmdline_arg(cmd, "remoting-auth-token")
            if port and token:
                return int(port), token
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None


def _creds_from_lockfile() -> tuple[int, str] | None:
    # lockfile format: ProcName:PID:PORT:PASSWORD:PROTOCOL
    for path in _LOCKFILE_PATHS:
        try:
            with open(path) as f:
                parts = f.read().strip().split(":")
            if len(parts) >= 5:
                return int(parts[2]), parts[3]
        except (FileNotFoundError, OSError, ValueError):
            continue
    return None


_cached_creds: tuple[int, str] | None = None


def find_lcu_credentials(refresh: bool = False) -> tuple[int, str] | None:
    """Return (port, token) for the running client, or None if not running.

    Cached because port/token are stable for a client session; pass refresh=True
    after a failed request in case the client restarted with new credentials.
    """
    global _cached_creds
    if _cached_creds and not refresh:
        return _cached_creds
    _cached_creds = _creds_from_process() or _creds_from_lockfile()
    return _cached_creds


# ── request helpers ─────────────────────────────────────────────────────────

def _auth_header(token: str) -> str:
    return "Basic " + base64.b64encode(f"riot:{token}".encode()).decode()


def lcu_request(method: str, path: str, **kwargs) -> requests.Response:
    """Issue an LCU request, refreshing stale credentials once on failure."""
    creds = find_lcu_credentials()
    if not creds:
        raise LCUUnavailable("League client not running")

    for attempt in (0, 1):
        port, token = creds
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = _auth_header(token)
        headers["Accept"] = "application/json"
        try:
            return requests.request(
                method, f"https://127.0.0.1:{port}{path}",
                headers=headers, verify=False, timeout=5, **kwargs)
        except requests.RequestException:
            if attempt == 1:
                raise LCUUnavailable("League client unreachable")
            creds = find_lcu_credentials(refresh=True)  # client may have restarted
            if not creds:
                raise LCUUnavailable("League client not running")


def _get_json(path: str, allow_404: bool = False):
    resp = lcu_request("GET", path)
    if allow_404 and resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


# ── endpoint wrappers ───────────────────────────────────────────────────────

def get_gameflow_phase() -> str:
    """Current client phase: None|Lobby|Matchmaking|ReadyCheck|ChampSelect|InProgress|…"""
    return _get_json("/lol-gameflow/v1/gameflow-phase")


def get_champ_select_session() -> dict | None:
    """Live draft session, or None when not in champ select (404)."""
    return _get_json("/lol-champ-select/v1/session", allow_404=True)


def get_perks_metadata() -> list:
    """All rune perks (id, name, …) for name→ID resolution."""
    return _get_json("/lol-perks/v1/perks")


def get_styles_metadata() -> list:
    """All rune styles/trees (id, name, slots) for name→ID resolution."""
    return _get_json("/lol-perks/v1/styles")


def get_current_rune_page() -> dict | None:
    return _get_json("/lol-perks/v1/currentpage", allow_404=True)


def get_rune_pages() -> list:
    return _get_json("/lol-perks/v1/pages") or []


def get_champion_summary() -> dict[int, str]:
    """Champion id → name, sourced from the client's own asset bundle."""
    data = _get_json("/lol-game-data/assets/v1/champion-summary.json") or []
    return {c["id"]: c["name"] for c in data}


def apply_rune_page(payload: dict) -> dict:
    """Create + select a rune page, replacing our own previous one.

    Only deletes a page named RUNE_PAGE_NAME (ours) or, failing that, an editable
    page when the inventory is full — never the player's other saved pages.
    """
    payload = {**payload, "name": RUNE_PAGE_NAME, "current": True}

    # Remove our previous page(s) so we don't accumulate duplicates.
    for p in get_rune_pages():
        if p.get("name") == RUNE_PAGE_NAME and p.get("isDeletable", True):
            lcu_request("DELETE", f"/lol-perks/v1/pages/{p['id']}")

    resp = lcu_request("POST", "/lol-perks/v1/pages", json=payload)
    if resp.status_code in (400, 409, 500):
        # Likely the page inventory is full — free one editable, non-default slot
        # (never the player's currently-selected page) and retry once.
        current_id = (get_current_rune_page() or {}).get("id")
        for p in get_rune_pages():
            if (p.get("isDeletable") and p.get("isEditable")
                    and p.get("id") != current_id):
                lcu_request("DELETE", f"/lol-perks/v1/pages/{p['id']}")
                break
        resp = lcu_request("POST", "/lol-perks/v1/pages", json=payload)

    resp.raise_for_status()
    return resp.json()
