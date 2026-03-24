# Game Client API

The Game Client APIs are served over HTTPS by the League of Legends game client and are only available locally for native applications.

---

## SSL / Root Certificate

The League of Legends client uses a **self-signed certificate**. To use the Game Client API locally, either ignore SSL errors or supply the root certificate.

**Quick test (insecure):**
```bash
curl --insecure https://127.0.0.1:2999/swagger/v3/openapi.json
```

**Swagger specs:**
```
https://127.0.0.1:2999/swagger/v2/swagger.json
https://127.0.0.1:2999/swagger/v3/openapi.json
```

---

## Live Client Data API

Provides data during an active game — general game info and per-player stats.

---

### All Game Data

```
GET https://127.0.0.1:2999/liveclientdata/allgamedata
```

Returns all available data. Useful for exploration; prefer targeted endpoints in production.

---

## Active Player

### Get Active Player

```
GET https://127.0.0.1:2999/liveclientdata/activeplayer
```

All data about the active (local) player.

```json
{
  "abilities": {},
  "championStats": {
    "abilityHaste": 0.0,
    "abilityPower": 0.0,
    "armor": 0.0,
    "armorPenetrationFlat": 0.0,
    "armorPenetrationPercent": 0.0,
    "attackDamage": 0.0,
    "attackRange": 0.0,
    "attackSpeed": 0.0,
    "bonusArmorPenetrationPercent": 0.0,
    "bonusMagicPenetrationPercent": 0.0,
    "cooldownReduction": 0.0,
    "critChance": 0.0,
    "critDamage": 0.0,
    "currentHealth": 0.0,
    "healthRegenRate": 0.0,
    "lifeSteal": 0.0,
    "magicLethality": 0.0,
    "magicPenetrationFlat": 0.0,
    "magicPenetrationPercent": 0.0,
    "magicResist": 0.0,
    "maxHealth": 0.0,
    "moveSpeed": 0.0,
    "physicalLethality": 0.0,
    "resourceMax": 0.0,
    "resourceRegenRate": 0.0,
    "resourceType": "MANA",
    "resourceValue": 0.0,
    "spellVamp": 0.0,
    "tenacity": 0.0
  },
  "currentGold": 0.0,
  "fullRunes": {},
  "level": 1,
  "summonerName": "Riot Tuxedo",
  "riotId": "Riot Tuxedo#TXC1",
  "riotIdGameName": "Riot Tuxedo",
  "riotIdTagLine": "TXC1"
}
```

---

### Get Active Player Name

```
GET https://127.0.0.1:2999/liveclientdata/activeplayername
```

Returns the player's Riot ID as a plain string.

```json
"Riot Tuxedo#TXC1"
```

---

### Get Active Player Abilities

```
GET https://127.0.0.1:2999/liveclientdata/activeplayerabilities
```

Abilities for the active player.

```json
{
  "E": {
    "abilityLevel": 0,
    "displayName": "Molten Shield",
    "id": "AnnieE",
    "rawDescription": "GeneratedTip_Spell_AnnieE_Description",
    "rawDisplayName": "GeneratedTip_Spell_AnnieE_DisplayName"
  },
  "Passive": {
    "displayName": "Pyromania",
    "id": "AnniePassive",
    "rawDescription": "GeneratedTip_Passive_AnniePassive_Description",
    "rawDisplayName": "GeneratedTip_Passive_AnniePassive_DisplayName"
  },
  "Q": {
    "abilityLevel": 0,
    "displayName": "Disintegrate",
    "id": "AnnieQ",
    "rawDescription": "GeneratedTip_Spell_AnnieQ_Description",
    "rawDisplayName": "GeneratedTip_Spell_AnnieQ_DisplayName"
  },
  "R": {
    "abilityLevel": 0,
    "displayName": "Summon: Tibbers",
    "id": "AnnieR",
    "rawDescription": "GeneratedTip_Spell_AnnieR_Description",
    "rawDisplayName": "GeneratedTip_Spell_AnnieR_DisplayName"
  },
  "W": {
    "abilityLevel": 0,
    "displayName": "Incinerate",
    "id": "AnnieW",
    "rawDescription": "GeneratedTip_Spell_AnnieW_Description",
    "rawDisplayName": "GeneratedTip_Spell_AnnieW_DisplayName"
  }
}
```

---

### Get Active Player Runes

```
GET https://127.0.0.1:2999/liveclientdata/activeplayerrunes
```

Full rune page for the active player.

```json
{
  "keystone": {
    "displayName": "Electrocute",
    "id": 8112,
    "rawDescription": "perk_tooltip_Electrocute",
    "rawDisplayName": "perk_displayname_Electrocute"
  },
  "primaryRuneTree": {
    "displayName": "Domination",
    "id": 8100,
    "rawDescription": "perkstyle_tooltip_7200",
    "rawDisplayName": "perkstyle_displayname_7200"
  },
  "secondaryRuneTree": {
    "displayName": "Sorcery",
    "id": 8200,
    "rawDescription": "perkstyle_tooltip_7202",
    "rawDisplayName": "perkstyle_displayname_7202"
  },
  "generalRunes": [ "..." ],
  "statRunes": [
    { "id": 5007, "rawDescription": "perk_tooltip_StatModCooldownReductionScaling" },
    { "id": 5008, "rawDescription": "perk_tooltip_StatModAdaptive" },
    { "id": 5003, "rawDescription": "perk_tooltip_StatModMagicResist" }
  ]
}
```

---

## All Players

### Get Player List

```
GET https://127.0.0.1:2999/liveclientdata/playerlist
```

All champions in the game with stats.

```json
[
  {
    "championName": "Annie",
    "isBot": false,
    "isDead": false,
    "items": [],
    "level": 1,
    "position": "MIDDLE",
    "rawChampionName": "game_character_displayname_Annie",
    "respawnTimer": 0.0,
    "runes": {},
    "scores": {},
    "skinID": 0,
    "summonerName": "Riot Tuxedo",
    "riotId": "Riot Tuxedo#TXC1",
    "riotIdGameName": "Riot Tuxedo",
    "riotIdTagLine": "TXC1",
    "summonerSpells": {},
    "team": "ORDER"
  }
]
```

---

### Get Player Scores

```
GET https://127.0.0.1:2999/liveclientdata/playerscores?riotId={riotId}
```

Current scores for a player.

```json
{
  "assists": 0,
  "creepScore": 0,
  "deaths": 0,
  "kills": 0,
  "wardScore": 0.0
}
```

---

### Get Player Summoner Spells

```
GET https://127.0.0.1:2999/liveclientdata/playersummonerspells?riotId={riotId}
```

Summoner spells equipped by a player.

```json
{
  "summonerSpellOne": {
    "displayName": "Flash",
    "rawDescription": "GeneratedTip_SummonerSpell_SummonerFlash_Description",
    "rawDisplayName": "GeneratedTip_SummonerSpell_SummonerFlash_DisplayName"
  },
  "summonerSpellTwo": {
    "displayName": "Ignite",
    "rawDescription": "GeneratedTip_SummonerSpell_SummonerDot_Description",
    "rawDisplayName": "GeneratedTip_SummonerSpell_SummonerDot_DisplayName"
  }
}
```

---

### Get Player Main Runes

```
GET https://127.0.0.1:2999/liveclientdata/playermainrunes?riotId={riotId}
```

Keystone and rune trees for any player.

```json
{
  "keystone": {
    "displayName": "Electrocute",
    "id": 8112,
    "rawDescription": "perk_tooltip_Electrocute",
    "rawDisplayName": "perk_displayname_Electrocute"
  },
  "primaryRuneTree": {
    "displayName": "Domination",
    "id": 8100,
    "rawDescription": "perkstyle_tooltip_7200",
    "rawDisplayName": "perkstyle_displayname_7200"
  },
  "secondaryRuneTree": {
    "displayName": "Sorcery",
    "id": 8200,
    "rawDescription": "perkstyle_tooltip_7202",
    "rawDisplayName": "perkstyle_displayname_7202"
  }
}
```

---

### Get Player Items

```
GET https://127.0.0.1:2999/liveclientdata/playeritems?riotId={riotId}
```

Items currently held by a player.

```json
[
  {
    "canUse": true,
    "consumable": false,
    "count": 1,
    "displayName": "Warding Totem (Trinket)",
    "itemID": 3340,
    "price": 0,
    "rawDescription": "game_item_description_3340",
    "rawDisplayName": "game_item_displayname_3340",
    "slot": 6
  }
]
```

---

## Events

### Get Event Data

```
GET https://127.0.0.1:2999/liveclientdata/eventdata
```

All events that have occurred in the game so far.

```json
{
  "Events": [
    {
      "EventID": 0,
      "EventName": "GameStart",
      "EventTime": 0.032556
    }
  ]
}
```

---

## Game

### Get Game Stats

```
GET https://127.0.0.1:2999/liveclientdata/gamestats
```

Basic metadata about the current game.

```json
{
  "gameMode": "CLASSIC",
  "gameTime": 0.0,
  "mapName": "Map11",
  "mapNumber": 11,
  "mapTerrain": "Default"
}
```

---

## Notes

- Parameters that previously accepted `summonerName` now accept `riotId` (e.g. `Riot Tuxedo#TXC1`).
- The API attempts to match: **riotId** → **riotIdGameName** → **summonerName** (backwards-compat fallback).
