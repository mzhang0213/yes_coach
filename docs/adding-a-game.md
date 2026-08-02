# Adding a game

Yes Coach is a game-agnostic coaching overlay. The generic framework lives in
`server/core/`; each game is a self-contained **adapter** under `server/games/`.
`server/main.py` picks the active adapter at startup and never imports a
concrete game.

## Quick start

1. Copy the scaffold:
   ```
   cp -r server/games/_template server/games/<yourgame>
   ```
2. In `adapter.py`, set `name = "<yourgame>"` and `display_name`, and implement
   `is_active()` (detect whether your game is running).
3. Fill in the seams below.
4. Run it:
   ```
   YESCOACH_GAME=<yourgame> python -m server.main
   ```
   Without the env var, `main.py` auto-selects the first adapter whose
   `is_active()` returns true, else defaults to `lol`.

Adapters self-register on import (the `register(...)` line at the bottom of
`adapter.py`). `registry.discover()` imports every `games/<name>/adapter.py`,
skipping `_`-prefixed folders like `_template`.

## The seams (`server/core/`)

| Seam | File | What it does |
|---|---|---|
| `GameAdapter` | `core/adapter.py` | Bundles everything below; the composition root. |
| `StateSchema` | `core/schema.py` | Declares your compact coaching-state fields once. |
| `Coach` / `CoachProfile` | `core/coach.py` | The Gemini engine + your persona/schemas. |
| `DataSource` / `PollingDataSource` | `core/datasource.py` | Background producer thread(s). |
| `CheckpointRules` / `Checkpoint` | `core/checkpoints.py` | *When* the coach proactively speaks. |
| `TrendRules` | `core/trends.py` | Deltas over a snapshot window. |
| `UICards` / `ActionZone` | `core/ui_cards.py` | Game-specific overlay cards + hover-fill buttons. |
| `TabAction` | `core/adapter.py` | The hover-menu tabs. |

## What to implement

1. **State** (`state.py`) — declare your `StateSchema` fields and a `build_state`
   that strips a raw signal frame to that compact dict. Add a game-state class
   whose `compressed_state()` returns it.
2. **Data source** (`source.py`) — subclass `PollingDataSource` and implement
   `_poll_once` to fetch a frame and write it onto `session.game` / set
   `session.ui.in_game`. Three signal types fit the same base:
   - **local-API realtime** (like LOL): HTTP/IPC fetch each cycle.
   - **vision-only**: read `server.utils.SCREEN_CAP.last_frame` and run CV.
   - **push/turn-based**: implement the `DataSource` Protocol (`start`/`stop`)
     directly with a blocking listener instead of subclassing.
3. **Coach profile** (`coach_config.py`) — a `CoachProfile(system_prompt, schemas)`.
4. **Tabs** (`tabs.py`) — a list of `TabAction(label, question, schema_key)`.
5. **UI cards** (`ui_cards.py`) — `phase_label`, `draw_pregame`, `draw_ingame`.
   Return `[]` for pill-only; return `ActionZone`s for hover-fill buttons.
6. **Adapter** (`adapter.py`) — wire it all together and `register(...)`.

### Minimum viable adapter

Everything except state, one data source, a coach profile, and `tab_actions` is
optional. A vision-only game with no pre-game, checkpoints, or trends needs only
those four — `ui_cards` may return `[]` and `data_sources` a single source.

## Reference implementation

`server/games/lol/` is the full reference: a local-API realtime game with two
data sources (in-game `:2999` + pre-game LCU), champ-select draft parsing, a
rune card with an LCU write-back `ActionZone`, objective-timer checkpoints, and
trend deltas. Read it alongside the seams above.

## Verify

- `YESCOACH_GAME=<yourgame> python -m server.main` boots and shows the status
  pill.
- `server/core/` imports nothing from `server/games/` (the framework stays
  game-agnostic); `main.py` never imports your adapter directly.
