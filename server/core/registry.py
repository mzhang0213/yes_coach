"""Adapter registry + discovery.

Each game package exposes an `adapter` module that calls `register(...)` at
import. `discover()` imports every `server.games.<name>.adapter` (skipping
underscore-prefixed folders like `_template`) so each self-registers. `main.py`
then selects the active adapter by env override, auto-detection, or default.
"""

import importlib
import os

_ADAPTERS: dict = {}


def register(adapter) -> None:
    _ADAPTERS[adapter.name] = adapter


def discover() -> None:
    """Import each `server.games.<name>.adapter` so it self-registers.

    Scans the filesystem rather than pkgutil.iter_modules because the games are
    PEP-420 namespace packages (no __init__.py), which iter_modules skips.
    Underscore/dot-prefixed folders (e.g. `_template`) are ignored.
    """
    import server.games as games_pkg
    for base in games_pkg.__path__:
        for name in sorted(os.listdir(base)):
            if name.startswith(("_", ".")):
                continue
            pkg = os.path.join(base, name)
            if os.path.isdir(pkg) and os.path.exists(os.path.join(pkg, "adapter.py")):
                importlib.import_module(f"server.games.{name}.adapter")


def get(name: str):
    return _ADAPTERS[name]


def active():
    """First registered adapter whose game is currently running, or None."""
    for a in _ADAPTERS.values():
        try:
            if a.is_active():
                return a
        except Exception:
            continue
    return None


def all_adapters() -> dict:
    return dict(_ADAPTERS)
