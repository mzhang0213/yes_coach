# yes_coach — Flows & Architecture

How the overlay coach moves through game state, and what happens when.

## Big picture

There are **two independent axes of "state"** running at once, driven by
different clocks:

1. **The overlay UI state machine** — the hover-fill button animation
   (`idle → filling → unfurled → closing → cooldown`), driven by the 60fps
   render tick.
2. **The game/session lifecycle** — where you are in a League session
   (`NotRunning → ChampSelect → InProgress → game end`), driven by two
   background pollers.

Everything is wired together in `server/main.py`. Structure is MVC
(`model.py` / `view.py` / `controller.py`) plus background services under
`server/resources/`.

## Threading model (who runs when)

`main.py:32-55` sets up four concurrent execution contexts:

| Thread | What it does | Cadence |
|---|---|---|
| **Main / Qt** | `controller.tick()` → reads model, renders overlay, hit-tests cursor | every **16ms (~60fps)** |
| **`GameStatePoller`** | polls the Riot **Live Client** (`:2999`) for in-game data | every **1.5s**, daemon thread |
| **`ClientPoller`** | polls the **LCU** (League client) `gameflow-phase` + champ select | every **1.5s**, daemon thread |
| **`ScreenCapture`** | grabs frames for minimap CV | continuous (`utils.py`) |

Key design rule: **the tick loop never touches the network or the LLM.** It
only reads state the pollers already wrote onto the model, animates, and
hit-tests. All slow work (HTTP, Gemini calls) happens off-thread and stashes
results back on the model (`controller.py:40-50`, `poller.py`,
`client_poller.py`). Threads share the model without a lock — writes are
single-field assignments, reads are on tick.

## Axis 1: The session lifecycle

The two pollers hit two different endpoints, and which one responds tells you
the phase:

```
NotRunning ──► ChampSelect ──► InProgress ──► (game ends)
   LCU:         LCU responds    :2999 responds   :2999 unreachable
NotRunning      :2999 dead      → in_game=True   → in_game=False
```

`model.in_game` (set at `poller.py:115`, cleared in `_end_game` at
`poller.py:141`) is the master switch. It's `True` only while the Live Client
`:2999` is reachable — i.e. actually in a game.

### Pre-game (ClientPoller — `client_poller.py`)

Each 1.5s cycle (`_poll_once`, line 142):

1. Reads `gameflow-phase` → writes `model.phase` (drives the status pill text).
2. If not `ChampSelect`, resets pre-game state and returns.
3. In `ChampSelect`: fetches the champ-select session, runs `parse_draft()`
   (line 32) into a compact dict (`my_role`, picks, bans, `on_the_clock`,
   `phase_action`) → `model.draft`.
4. `_on_draft_change` (line 163) dedups via a `draft_signature` hash so it only
   acts on **meaningful** changes, and only when it's actually your turn:
   - **Your champ just locked** → `_advise_loadout`: asks Gemini for
     runes+spells (`loadout` schema), then `build_rune_payload` resolves
     names→perk IDs → `model.rune_recommendation`.
   - **On the clock to ban/pick** → `_advise`: asks Gemini with the `ban`/`pick`
     schema → `model.pregame_suggestion`.

All of these fire on their own worker threads (lines 188, 201).

### In-game (GameStatePoller — `poller.py`)

The orchestration seam. Each `_poll_once` (line 79):

1. **Fetch** — `get_active_player / game_stats / player_list / player_scores /
   event_data` via `riot.py`.
2. **Detect game boundaries** — `_maybe_new_game` (line 119) opens a new SQLite
   `games` row on first poll, or when the game clock runs backwards
   (restart/new game).
3. **Route into model** — `update_active_player / update_game_stats /
   update_players / update_events`, which reuse `_api_filter`
   (`model.py:102`) to strip to coaching-relevant fields.
4. **Vision** — `vision.summarize()` crops the minimap from the shared screen
   frames, color-masks champion blips, and emits a one-line text summary like
   `enemies_visible:3/5 enemy_near_dragon:y` → `model.map_summary`
   (`vision_service.py:77`). Zero token cost — merged into the prompt as text.
5. **Persist** — writes the compressed snapshot + new events to SQLite
   (`snapshot_store.py`).
6. **Trends** — `compute_trends` (line 108) reads the last ~5min of snapshots
   and derives *deltas* (cs/min change, gold delta, kda velocity, death streak)
   so the LLM sees change, not raw history.
7. **Checkpoints** — `detector.check()` decides *when* to speak up.

## The proactive coach flow (checkpoints)

`checkpoints.py` is the "when should the coach interrupt you" brain. Every poll,
`check()` (line 59) evaluates three trigger classes, each de-duplicated by a
`key` in a `_fired` set so it speaks **once**, not every 1.5s:

- **Time marks** — 15:00, 20:00 (`_TIME_MARKS`).
- **Computed spawns** — objectives the API never announces but whose timing is
  deterministic: first drake 5:00, drake respawn 5min after a `DragonKill`,
  baron 20:00 — pre-warned ~30s ahead, flagged `want_image=True`.
- **Events** — dragon/baron/tower/multikill/etc. from the live event feed, plus
  **death streaks** surfaced by trends.

When a checkpoint fires (`_handle_checkpoint`, `poller.py:154`):

1. Appended to `model.checkpoints`.
2. If it's a map-dependent decision (`want_image`), `vision.minimap_image()`
   returns a cropped PIL minimap for a **multimodal** Gemini call.
3. `coach.get_advice()` runs with the checkpoint's schema + state + trends + map
   context → result lands on `model.pending_suggestion` / `model.last_advice`
   for the UI to surface.

## The Gemini call itself (`gemini.py`)

`LoLCoach._call` (line 154) builds a tiny prompt:
`schema:{...} state:{...} context:{...} question:...`. The schema (from
`schemas.py`) is sent inline every turn so the model returns exactly-shaped
JSON. Notable bits:

- **Key rotation** — cycles through multiple `GEMINI_API_KEY*` env vars; on a
  429/quota error it re-inits with the next key and retries (line 205).
- **History pruning** — caps chat history at 12 recent messages while preserving
  seeded "last game" memory (line 143), keeping token cost flat over a long
  game.
- **Session memory** — `end_session` saves a compact game summary to
  `coach_memory.json`, re-injected as a 2-message exchange next launch
  (line 84).
- One shared chat guarded by a lock because poller + UI threads both call it
  (line 179).

## Axis 2: The overlay UI state machine (`controller.tick`)

The micro-loop, 60fps. `tick()` (`controller.py:103`):

```
view.render(model) → geom     (view decides what's on screen)
  geom is None             → not in game. ignore all input.
  geom has 'apply'         → champ-select rune card: only Apply button is live
  geom has main/left/right → in-game overlay: run the hover state machine
```

`view.render` (`view.py:761`) gates it all:

- **Not in game** → draws a phase-aware **status pill** and returns `None`. In
  champ select it additionally draws the **rune card** (returning
  `{'apply': box}`) or ban/pick advice text.
- **In game** → draws the "Ask Coach!!" button, plus side tabs when unfurled,
  and returns `{main, left, right}` boxes.

The controller then hit-tests the cursor (`pyautogui.position()`) against those
boxes and advances the hover-fill state machine — every interaction is a
**dwell/hover-to-fill**, no clicks:

- `idle → filling`: cursor enters main button, bloom rises
  (`compl += 0.019`/frame).
- `filling → unfurled`: bloom reaches ~1.0 → side tabs appear.
- `unfurled`: hovering a **left tab** fills it → on full fill fires
  `_run_tab(i)` → `_TAB_INTENTS` (line 16) maps to a canned question + schema.
  Hovering the **right tab** (notebook icon) opens the free-text `PromptWindow`.
- `closing → cooldown → idle`: re-hovering main after leaving closes it.

The **user-triggered advice path** (`_run_advice`, line 34) mirrors the
checkpoint path: spawns a worker thread, calls `coach.get_advice` with
`model.compressed_state()` + map summary, and writes `model.last_advice` /
`model.pending_suggestion`.

The **Apply-runes path** (`_handle_apply_button`, line 91): during champ select,
hovering the rune card's Apply button fills it; on full fill `_apply_runes`
writes the resolved rune page to the client via LCU (`lcu.apply_rune_page`)
off-thread.

## One-line summary of "what happens when"

- **Client open, no game** → ClientPoller sets phase; overlay shows a status
  pill.
- **Champ select** → ClientPoller parses draft → on your turn Gemini gives
  ban/pick advice; on lock it gives a rune loadout you can hover-to-apply.
- **In game** → GameStatePoller polls every 1.5s, updates model, persists
  snapshots, runs minimap CV, computes trends, and fires checkpoints →
  proactive Gemini advice at key moments; meanwhile you can hover the overlay
  button anytime to ask for situational/comp/build advice or type a question.
- **Game ends** (`:2999` drops) → `in_game=False`, game row closed with a
  summary; overlay reverts to the pill.
