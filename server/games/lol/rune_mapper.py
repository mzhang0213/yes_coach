"""Resolve the coach's rune/spell *names* into the numeric IDs the LCU needs.

Gemini reliably knows rune and spell *names* but not Riot's perk IDs, so the
`loadout` schema returns names and this module maps them to IDs using the live
LCU metadata (`/lol-perks/v1/perks`, `/lol-perks/v1/styles`), then assembles the
`selectedPerkIds` page payload. Matching is fuzzy (exact → substring → closest)
so minor naming differences ("Coup de Grace" vs "Coup") still resolve.

Stat shards and summoner spells have stable IDs and aren't always in the perks
list, so they're hardcoded as a fallback and merged into the index.
"""

import difflib

# Stat shard IDs (stable). The same shard ID legitimately repeats across rows.
_SHARD_IDS = {
    "adaptive force": 5008,
    "attack speed": 5005,
    "ability haste": 5007,
    "move speed": 5010,
    "health scaling": 5001,
    "health": 5011,
    "tenacity": 5013,
    "tenacity and slow resist": 5013,
}

# Summoner spell IDs (stable).
SUMMONER_SPELL_IDS = {
    "barrier": 21, "cleanse": 1, "exhaust": 3, "flash": 4, "ghost": 6,
    "heal": 7, "ignite": 14, "smite": 11, "teleport": 12, "clarity": 13,
    "mark": 32, "snowball": 32,
}


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def build_name_index(perks_metadata: list) -> dict[str, int]:
    """name(lower) → perk id, from LCU perks metadata, plus stat-shard fallbacks."""
    index = {_norm(p["name"]): p["id"] for p in perks_metadata if p.get("name")}
    for name, pid in _SHARD_IDS.items():
        index.setdefault(name, pid)
    return index


def resolve(name: str, index: dict[str, int]) -> int | None:
    """Fuzzy-match a name to an ID: exact → substring → closest above cutoff."""
    key = _norm(name)
    if not key:
        return None
    if key in index:
        return index[key]
    for k, v in index.items():       # substring either direction
        if key in k or k in key:
            return v
    match = difflib.get_close_matches(key, list(index), n=1, cutoff=0.6)
    return index[match[0]] if match else None


def map_summoner_spells(names: list[str]) -> list[int]:
    ids = [SUMMONER_SPELL_IDS.get(_norm(n)) for n in (names or [])]
    return [i for i in ids if i]


def build_rune_payload(loadout: dict, perks_metadata: list,
                       styles_metadata: list) -> dict:
    """Build the LCU rune-page payload from a `loadout` recommendation.

    selectedPerkIds order: keystone, 3 primary minors, 2 secondary, 3 shards.
    Unresolved names are dropped (logged by the caller via the returned counts).
    """
    perks_idx = build_name_index(perks_metadata)
    styles_idx = {_norm(s["name"]): s["id"] for s in styles_metadata if s.get("name")}

    ordered = (
        [loadout.get("keystone")]
        + list(loadout.get("primary_runes") or [])[:3]
        + list(loadout.get("secondary_runes") or [])[:2]
        + list(loadout.get("shards") or [])[:3]
    )
    selected = [pid for pid in (resolve(n, perks_idx) for n in ordered) if pid]

    return {
        "primaryStyleId": styles_idx.get(_norm(loadout.get("primary_style")))
                          or resolve(loadout.get("primary_style"), styles_idx),
        "subStyleId": styles_idx.get(_norm(loadout.get("secondary_style")))
                      or resolve(loadout.get("secondary_style"), styles_idx),
        "selectedPerkIds": selected,
    }
