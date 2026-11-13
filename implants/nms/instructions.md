---
title: No Man's Sky Implant
summary: How to read the player's No Man's Sky Save with the nms Implant's nine read-only commands (status, inventory, bases, find, route, system, convert, saves, watch), read their output, brief play sessions, plan Routes and respond to watch events.
tags:
- no-mans-sky
- implant
- save
- inventory
- route-planning
implant_id: 61b7be77
---

## Run a Command

Run every command from the engine repo:

```bash
uv run copotron implant run nms status
```

The nine commands are `status`, `inventory`, `bases`, `find`, `route`, `system`, `convert`, `saves` and `watch`. Every command only reads; nothing writes to a Save. Flags are in `uv run copotron implant run nms <command> --help`. Vocabulary is in [implants/nms/GLOSSARY.md](GLOSSARY.md) in the engine repo, separate from Copotron's glossary; this memory uses its terms.

## Read the Output

- **stdout** holds the result: text by default, one JSON document with `--json` (`watch --json`: one JSON object per line). Parse `--json` whenever you reason over the data.
- **stderr** holds errors: an `nms: …` line, followed by indented candidates when a name is ambiguous, or argparse's `usage:` lines for bad usage.
- **Exit codes**: `0` ok; `1` a Requisition Check (`inventory --have`) is short, which is an answer, not a failure; `2` an error or bad usage. On `2`, read the stderr line: an ambiguous name lists its candidates, so re-run with a fuller name or the Portal Glyphs.
- **`schema`**: every `--json` document names its shape as `nms.<command>/1` (`nms.status/1`, `nms.inventory/1`, … `nms.watch/1`). Check it before reading fields. The dev-only `bench` command has neither `schema` nor `notes`.
- **`notes`**: every `--json` document carries a `notes` array, `[]` when there is nothing to say. In text, each note is a final `Note      …` line (in `watch` text, a final `| Note: …` segment). Notes are advice about the Implant; faults in the Save are `warnings` (`status`). Relay a note's content where it bears on the answer: the Personal Refiner note, or the `≈` same-Region estimate.
- **Stale Game Data Snapshot**: a note starting `Game data built for save version …` means the Save is newer than the bundled Item Catalog and key mapping. Then:
  1. Answer the question normally.
  2. Tell the player once per session that the game data is older than the Save, so some items may show raw ids and some fields may be missing.
  3. Report a raw id as the raw id. Name an item only from the Item Catalog.
  4. Leave the refresh to the developer: bump the pinned MBINCompiler tag, then rerun `implants/nms/tools/build_catalog.py`. You never run it.

## Pick the Save

- Default: the newest Save across every Account and Save Slot.
- One call: `--save PATH` reads that `.hg` file; `--slot N` reads the newest file (manual or autosave) of Save Slot N. `convert` and `saves` take neither.
- Persistent: `NMS_SAVE_PATH` in the engine `.env`. A folder replaces the platform's save root; a file pins that file unless `--slot` is given.
- `saves` lists Accounts and Save Slots and marks the default with `*`. `saves --quick` skips decoding, so it shows no Game Mode or summary and runs no staleness check.

```bash
uv run copotron implant run nms saves --quick
uv run copotron implant run nms status --slot 9
```

## Commands

### status

Where the player is and what they have: Save name and file, Game Mode, Active Context, play time, Address (Galaxy, Portal Glyphs, Signal Booster Code, Region), Star System and planet when discovered, wallet (units, nanites, quicksilver) and current ship.

### inventory

- No argument: one summary row per Container.
- `inventory CATEGORY` lists a Category's Containers with their stacks. Categories: `suit`, `refiner`, `ship` (current ship), `ships` (every ship), `multitool`, `freighter`, `storage`, `exocraft`, `ingredients`, `corvette`, `rocket-locker`, `fishing-platform`, `bait-box`, `food-unit`, `grave`, `salvage`.
- `--search TEXT` matches item names and ids by substring across every Container, totalled per name group (every id sharing a name), with amounts per Container.
- `--have ITEM:N …` is a Requisition Check across every Container. `ITEM` resolves in order: exact id (case-sensitive) to that id; exact name (any case) to its whole name group; id in another case; a substring of exactly one name to that name's group. A substring of several names exits `2` listing them. In `--json`, each requirement carries `ids: [...]`, `have`, `need`, `met`, `short` and `locations`.
- An item the Item Catalog can't name shows as its raw id.
- **Personal Refiner** (`refiner`): only the exosuit's Refiner (owner `Exosuit`, name `Personal Refiner`), shown even when empty. Fuel is a Container value, `Fuel 40%` in text and `fuel_pct` in `--json`. Each stack has a `role` of `output` or `input`; refining progress isn't shown. Its output and inputs count toward `--search` and `--have`. `inventory refiner` always carries a note that the Save doesn't reveal Refiners in Bases, on the freighter, in Exocraft or on the corvette, and that refining continues when the game loads. With no Personal Refiner installed, the Category is empty and the note starts `No Personal Refiner installed.`
- **Storage Chest** (`storage`, labelled `Storage 0` … `Storage 9`): shown when built at one of the player's Bases or holding items; `built` in `--json`. An unbuilt one that holds items reads `(no container built)`.
- **Exocraft** (`exocraft`): shown when Deployed, or when not Deployed but holding cargo, marked `(not deployed)`; `type` and `deployed` in `--json`.
- **Base Salvage Capsule** (`salvage`): what was left when a Base was destroyed.

```bash
uv run copotron implant run nms inventory --search carbon
uv run copotron implant run nms inventory --have Carbon:50 "Ferrite Dust:100"
uv run copotron implant run nms inventory refiner
```

### bases

- No argument: the player's own Bases, nearest first. `--all` adds Visited Bases.
- `bases NAME` shows one Base, matched exact name first, then substring; more than one match exits `2`. The detail lists its Base Parts as counts per name group under fixed categories (Power, Storage, Refining, Farming, Extraction, Travel, Terminals, Utility, Computer, Corvette), then one `+ N structural and decor parts` line for structural parts, decor, wiring and parts the Item Catalog can't name. Storage containers name their Storage Chest (`Storage Container ×2 (Storage 0, Storage 1)`). Positions aren't shown, and the Save holds nothing about what is left to build.
- `bases --has TEXT` lists the Bases holding a Base Part, nearest first, each with its matching parts. `TEXT` is a name substring (every match, never refused as ambiguous), an exact id, or a category key: `power`, `storage`, `refining`, `farming`, `extraction`, `travel`, `terminals`, `utility`, `base_computer`, `corvette_modules`. Collapsed parts never match. Own Bases by default, `--all` adds Visited Bases.
- `--json`: each Base has `part_count`; the detail adds `parts: {structural, groups: [{category, name, ids, count, chests?}]}`; `--has` adds `matches` per Base. `chests` counts from 0, matching the `Storage n` labels.
- Distances here read `~265 ly (same region)` for a Base in the player's Region.

```bash
uv run copotron implant run nms bases --has refining
uv run copotron implant run nms bases --has teleport --all
```

### find, route, system: places

These three resolve a place (a `route` Stop, `--from PLACE`, `system NAME`) by one name rule:

- `here` (the default) is the player's location; 12 Portal Glyphs are that Address in the player's current Galaxy.
- A name is matched exact, then prefix, then substring (any case), across own Bases, Star Systems, named planets, then Visited Bases. Visited Bases need `--all`; without it the command names the Visited Base and suggests `--all`.
- Several matches exit `2` with up to 5 candidates. Pick one with the player, then re-run with the fuller name or its Portal Glyphs.

Distances are `≈265 ly` between two Star Systems in one Region (the Save stores only the Region; the order inside a Region is arbitrary) and 0 inside one Star System. `--json` marks these `estimate: true` and adds a note.

- `find`: discovered planets near a place, nearest 10 by default (`--nearest N`, or `--within LY`), filtered by `--biome`, `--infested` / `--not-infested`, `--named`, `--discoverer mine|others`. Only the start's Galaxy is searched; `other_galaxy` counts the matches left out.
- `route STOP …`: a Route from `--from` (default here) through the Stops, ordered nearest first then by 2-opt; `--keep-order` visits them as listed, `--round-trip` returns to the start. `route --biome B` is a Biome Tour of the nearest 5 matching planets (`--nearest N`, plus `find`'s filters); Stops and `--biome` are exclusive. A Stop in another Galaxy is refused. Warp Jumps show only with `--warp-range LY`; the Save doesn't hold the Warp Range, so ask the player for it.
- `system [NAME]`: one Star System (default here): discovered or not, its discoverer, its planets with the matched one marked, and the Bases in it.

```bash
uv run copotron implant run nms find --biome Lush --nearest 3
uv run copotron implant run nms route --biome Lush --warp-range 2500
uv run copotron implant run nms system here
```

### convert

Converts one Address between Portal Glyphs (hex, emoji or names), a `0x` galactic address, a Signal Booster Code (`XXXX:YYYY:ZZZZ:SSSS`) and a Region (`x,y,z` plus `--system N`). `--galaxy` takes an index, `#N` or a name and defaults to Euclid; `--planet` sets the planet. It reads no Save.

```bash
uv run copotron implant run nms convert 005FFEDBE6A5 --galaxy Euclid
```

## Brief a Session

- **Pre-session**: run `status` and `inventory --have` for the materials the current goal needs. Goals come from the session's context (the campaign and its roadmap, what the player has said). Say where the player is, what they hold toward the goal, and what is short.
- **Post-session**: run the same two commands again and report what changed against the pre-session briefing: goals met or still short, currencies, location.

## Plan Travel

Galaxy-scale Legs run to hundreds of Warp Jumps (694,544 ly is 278 at a 2,500 ly Warp Range), so players cross them by portal. When a Leg needs more Warp Jumps than a session allows, give the player the Stop's Portal Glyphs (the glyphs column of `route`, `find` and `bases`) to dial at a portal. Portal Glyphs carry no Galaxy, so the player must already be in the Stop's Galaxy.

## Watch the Game

`watch` prints one line per Save Update, carrying that Save Slot's Save Delta, until it is stopped or goes 60 minutes without a Save Update (`--idle-exit`). It watches every Save Slot unless `--slot`, `--save` or `NMS_SAVE_PATH` narrows it, and persists nothing.

1. **Start** only when the player asks for it. Being told they are playing is not a request. Run it as a background task from your own terminal; delivery fails from a shell outside the harness.
   - **Claude Code**: run it under the Monitor tool, which wakes the session once per stdout line:
     ```bash
     uv run copotron implant run nms watch
     ```
   - **Antigravity**: pipe each line to your own conversation. Take the conversation id from your artifact directory path (`<appData>/brain/<conversation-id>/`), or from `$env:ANTIGRAVITY_CONVERSATION_ID` when it is set. In PowerShell:
     ```powershell
     uv run copotron implant run nms watch | ForEach-Object { agentapi send-message <conversation-id> $_ }
     ```
2. **Read each line.** Text reads `[nms watch] Save updated: slot 3 (save5.hg) at 14:02:11 | +120 Chromatic Metal (512) | -1,200 Units | moved to Ekoxim IV`. The segments after the first are the Save Delta: inventory gained or lost by name group with the new total, currencies, new Star Systems and planets, own Bases added, edited or removed, location, Game Mode. `no changes` is an empty Save Delta. `no baseline` is the first Save Update seen from that Save Slot, so nothing is compared. A Save Slot's manual save and autosave share a baseline, so the second of the pair usually reads `no changes`. With `--json`, each line is an `nms.watch/1` object with `slot`, `account`, `kind`, `path`, `modified`, `baseline`, `changes` (`null` without a baseline) and `notes`. Startup messages and unreadable-Save warnings go to stderr. Exit `0` on idle or stop, `2` when the save folder disappears.
3. **Respond** from the session's own context; goals are whatever the session already holds. Read the Save Delta first; running follow-up commands is your call.
   - **Goal speech**, with one concrete next step taken from the session's context ("Refine the 120 Chromatic Metal, then fabricate the Auto-Charger."), when a goal's condition is newly met, when a met condition is lost (crafting used up the materials), or when something notable happens without a goal: a Game Mode change, a Base removed, a `no baseline` line from a Save Slot the player isn't playing.
   - **Engagement**: one short line in the inherited Persona's voice, reacting to the change, on every other non-empty Save Delta. It carries no suggestion unless the player asks.
   - **Silence** on `no changes`.
   - Lines that arrive while you are still replying get one combined message.
4. **Record** nothing in reaction to a watch line: no vault writes, and Tasks stay open. Normal crystallization applies: phase transitions, session close, or the player asking.
5. **Stop** the background task when the player asks. `--idle-exit` is the backstop.
