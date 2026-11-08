# Which Maintenance Interactions Are the Player's Refiners

Research for [#21](https://github.com/NafisAli/copotron-engine-r1/issues/21) (parent decision [#20](https://github.com/NafisAli/copotron-engine-r1/issues/20)). Date: 2026-11-09. This branch is never merged.

## Verdict

**(b) Heuristic only.** One narrow rule is reliable. Nothing in the save reliably identifies base or freighter refiners, or ties them to the player.

- **Reliable (a), exosuit Personal Refiner only.** It is the `PersonalMaintenanceInteractions[i]` whose paired key `StoredInteractions[Personal_Maintenance].Interactions[i]` has `GalacticAddress == 0` and `Position == (1, 1, 1, 1)`. It matched in all 26 saves: present in the 9 save pairs where the exosuit has `SUIT_REFINER`/`SUIT_REFINER2` installed, absent in the 4 pairs without it.
- **Heuristic, portable refiner placed in an owned base.** The base object `^BUILD_REFINER1` is matched to a `MaintenanceInteractions` entry by the same `GalacticAddress` plus the same direction from the planet centre. This works when an entry exists, but the save only gives a hit in 1 of 6 owned base refiners/cookers.
- **Not determinable (c), medium/large base refiners, freighter refiners and portable refiners outside bases.** Medium/large/freighter/corvette refiners have no `MAINT_FUEL*` slot at all, so the candidate rule cannot see them. Their containers (`MAINT_REFINER` placeholder plus items) look the same as the new utility modules. Owned base machines mostly have no maintenance entry, and freighter-interior keys could not be aligned with `FreighterBase` objects.

**The candidate rule ("a `MAINT_FUEL*` slot plus at least one non-`MAINT_*` item") is not sound.** Across one save of each of the 14 decodable save pairs it fires 82 times. Only 5 of those hits can be attributed to a live player refiner: 4 exosuit refiners and 1 base portable refiner. The others are:

| Rule hits (14 saves) | What they are | Evidence |
|---|---|---|
| 26 | `MAINT_FUEL1` + one item at slot X1: refiner output, **or a harvester** | Atmosphere harvester pre-installs `MAINT_FUEL1`+`GAS1`; mineral harvester pre-installs `MAINT_FUEL1`+`YELLOW2` (game data, below) |
| 10 | `MAINT_FUEL1` + `GAS*` only: almost certainly atmosphere harvesters | same |
| 2 | `MAINT_FUEL4` + `OXYGEN`/`ANTIMATTER`: oxygen / antimatter harvesters | game data |
| 14 | "ghost" refiners keyed at the `(1,1,1,1)` sentinel inside `MaintenanceInteractions`, timestamps 2020–2023, several per save | saves |
| 26 | `MAINT_FUEL1` + an item at X2: a running fuel-type refiner (portable, exosuit or exocraft), owner/location unknown except 1 | saves + recipe table |

Known false negatives: every medium/large/freighter/corvette refiner, every idle refiner (fuel + `MAINT_REFINER` placeholder, no items), and any base refiner whose entry is missing.

## Q1. What the `Flags` bits mean

**Answer:** `Flags` encodes **state, not object type**. No source names the bits; the layout below comes from the saves.

- **libMBIN (high trust):** `GcMaintenanceContainer.Flags` is a plain `ushort` (field index 6) with no enum or bitfield annotation. The other fields are `InventoryContainer`, `LastUpdateTimestamp`, `LastCompletedTimestamp`, `LastBrokenTimestamp`, `DamageTimers` (`List<float>`) and `AmountAccumulators` (`List<float>`). Source: `libMBIN/Source/NMS/GameComponents/GcMaintenanceContainer.cs`, MBINCompiler `development` @ `59987b2` (2026-11-04).
- **Saves (measured, medium trust; 26 saves, every entry of both lists):**
  - **bit 15 (0x8000):** set on every `PersonalMaintenanceInteractions` entry in saves of version 4647 and later. Legacy saves 4626/4628 use bit 13 (0x2000) for the same entries. It also appears on some `MaintenanceInteractions` refiner entries. It is not a type marker: repair, portal and refiner entries all carry it.
  - **bits 0–1:** 1 or 2 on repair-type containers (`MAINT_TECH*`, `MAINT_PORTAL*`, `MAINT_FUEL3`). Value 1 goes with completed or repaired entries (non-zero `LastCompletedTimestamp`, slot amounts ≥ 50). Value 2 goes with incomplete ones (amounts < 50). Of 50 unique entries, 44 follow this pattern; it does not hold everywhere.
    - `0x8001` (32769) = bit 15 + "complete"
    - `0x8002` (32770) = bit 15 + "not complete"
  - **bits 3–14:** a 12-bit counter on refiner-unit containers equal to `min(DamageTimers[1], 4095)`. This held in 58 of 68 unique fuel-type refiner entries.
    - `0x8E00` (36352) = bit 15 + 448<<3: save16 exosuit refiner, `LAND1` ×448, `DamageTimers[1] = 448`.
    - `0x8660` (34400) = bit 15 + 204<<3: save17 exosuit refiner, output 150 + input 54 = 204 = `DamageTimers[1]`.
    - `0xFFF8` (65528) = bit 15 + 4095<<3: save23, 964 + 7235 items, `DamageTimers[1]` saturated at 4095.
  - **bit 2 (0x4):** set on some refiner entries; meaning unknown.
  - 19,388 of the 19,566 `MaintenanceInteractions` entries across all saves have `Flags == 0`, including idle refiners.
- Conclusion: `Flags` cannot classify an entry. At most it gives a progress hint for refiners that are already identified.

## Q2. What game data and reference tools say

**Game data (highest trust).** Files were copied from `E:\SteamLibrary\...\No Man's Sky\GAMEDATA\PCBANKS` (PAKs dated 2026-11-05/06), unpacked with hgpaktool 1.1.3 and converted with MBINCompiler **v7.10.0-pre1** (released 2026-10-28).

- **Refiners are identified by a component, not by anything in the save.** Every machine that refines carries `GcRefinerUnitComponentData` (`MaintenanceData: GcMaintenanceComponentData`, `NumInputs`, `IsCooker`). The struct is in libMBIN `GcRefinerUnitComponentData.cs`. These 17 entities carry it:

  | Entity | Title key | Pre-installed maintenance elements | NumInputs | IsCooker |
  |---|---|---|---|---|
  | `tech/refiner/refiner1` (`BUILD_REFINER1`, portable) | `REFINER1_NAME_L` | `MAINT_FUEL1`, `MAINT_REFINER` | 1 | false |
  | `player/playercharacter` (exosuit Personal Refiner) | `UI_SUIT_REFINER_NAME_L` | `MAINT_FUEL1`, `MAINT_REFINER` | 1 | false |
  | `vehicles/rover` (exocraft refiner) | `UI_EXO_REFINER_NAME_L` | `MAINT_FUEL1`, `MAINT_REFINER` | 3 | false |
  | `tech/refiner/refiner2` (`BUILD_REFINER2`, medium) | `REFINER2_NAME_L` | `MAINT_REFINER` only | 2 | false |
  | `tech/refiner/refiner3` (`BUILD_REFINER3`, large) | `REFINER3_NAME_L` | `MAINT_REFINER` only | 3 | false |
  | `freighterbase/rooms/refinerroom/.../refinerterminal` (`FRE_ROOM_REFINE`) | `REFINER3_NAME_L` | `MAINT_REFINER` only | 3 | false |
  | `spacecraft/biggs/refiner` (corvette) | `BLD_BIG_WALL_REF_NAME_L` | `MAINT_REFINER` only | 3 | false |
  | `utilityparts/module_{battery,coolingtower,pump,silo,solarpanel,windturbine}` | `REFINER1_NAME_L` | `MAINT_REFINER` only | 1 | false |
  | cookers: `tech/cooker` (`COOKER`), biggs cooker, skiff cooker, nexus grill | `UI_OVEN_NAME_L`, … | `MAINT_COOKER` only | 3 | true |

- **Only fuel-burning refiners have a `MAINT_FUEL1` slot** (`MAINT_FUEL1` = "Fuel Inverter", `MAINT_REFINER` = "Refinery Output"). In `refiner1`, `MAINT_FUEL1` has `CompletionRequirement = AnyChargeAndRepaired` and `AmountEmptyTimePeriod = 300`. `MAINT_REFINER` has `CompletionRequirement = HasIngredients` and `AmountEmptyTimePeriod = 30`.
- **`MAINT_FUEL*` is shared with non-refiners** (byte search of every unpacked `*.entity.mbin`, then conversion):
  - `MAINT_FUEL1`: atmosphere harvester (`gasharvester`, pre-installs `GAS1`) and mineral harvester (`resourceharvester`, pre-installs `YELLOW2`)
  - `MAINT_FUEL2`: salvage terminal
  - `MAINT_FUEL3`: holocom
  - `MAINT_FUEL4`: oxygen harvesters (`OXYGEN`) and antimatter harvester (`ANTIMATTER`)
- **`basebuildingobjectstable`:** `BUILD_REFINER1` has `BuildableOnPlanet = true`, `BuildableOnFreighter = true` and `CanPickUp = true`, so it is the portable refiner. `BUILD_REFINER2` and `BUILD_REFINER3` are base-only with `CanPickUp = false`. `FRE_ROOM_REFINE` is freighter-only.
- **`nms_reality_gcrecipetable`:** 1,684 recipes, 361 of them non-cooking, each `GcRefinerRecipe {Id, TimeToMake, Cooking, Result, Ingredients}`. Recipes are global and not attached to a container.
- `DamageTimers` has one entry per pre-installed element: 2 for fuel-type refiners and 1 for `MAINT_REFINER`-only refiners. This matches the save data. The pairing is inferred, not documented.

**libMBIN structure (high trust).** `GcPlayerStateData.cs` @ `59987b2`:

- `MaintenanceInteractions` (field 65) and `PersonalMaintenanceInteractions` (field 66) are `List<GcMaintenanceContainer>`. They carry no key.
- The keys live in `StoredInteractions` (field 64), a fixed array `GcInteractionBuffer[0xB]` indexed by `GcInteractionBufferType`:
  - index 7 = `Maintenance`
  - index 9 = `Personal_Maintenance`
- `GcInteractionBuffer` = `{List<GcInteractionData> Interactions, int CurrentPos}`.
- `GcInteractionData` = `{Vector4f Position, ulong GalacticAddress, ulong Value}`.
- Also present: `RefinerBufferData` (field 247, `List<GcMaintenanceContainer>`) and `RefinerBufferKeys` (field 246, `List<GcMaintenanceSaveKey {Vector3f Position, int Location}>`). `Location` is a plain `int`, no enum.

**Save editors (medium trust).** None shows or edits refiner contents.

- **NMSE** (vectorcmdr/NMSE @ `e922f37`, 2026-11-03): no reference to `MaintenanceInteractions`, `PersonalMaintenanceInteractions`, `StoredInteractions` or `RefinerBuffer*` outside its bundled `mapping.json`. The only refiner mention is a display label for `^FRE_ROOM_REFINE` in `Core/FreighterLogic.cs`.
- **NomNom** (zencq/NomNom @ `f3fa972`) and **libNOM.io** (`652aabb`): no references.
- **goatfungus NMSSaveEditor** 1.21.0 (jar @ `6047315`): `Application.class` contains the string `PlayerStateData.MaintenanceInteractions` next to the menu strings "Recharge Base Planters" and "Repair All Slots / Technology". The code is obfuscated and was not decompiled (no JDK available), so how it uses the list is unverified. Its README lists no refiner feature.

**Community sources:** not consulted. The primary sources were enough.

## Q3. Can entries be tied to bases, positions or the player?

**The key is positional.** Saves give high trust here; libMBIN gives the field layout.

- `MaintenanceInteractions[i]` pairs with `StoredInteractions[7].Interactions[i]`, and `PersonalMaintenanceInteractions[i]` with `StoredInteractions[9].Interactions[i]`.
  - Checked in every save that has the 11-slot buffer, 22 files: each populated entry has a populated key, and each empty entry has an empty key (`Position.w == -1`). There were no exceptions; 2 trailing entries in save7/8 sit beyond the 1,000-slot key buffer.
  - Older saves (`save.hg`, `save2.hg`, version 4616) have only 8 buffer types and were not checked.
- A key is the planet-level `GalacticAddress` plus a planet-relative `Position` (w = 1). There is no base id and no object id. `PersistentPlayerBases[*].Objects[*].UserData` holds small values such as 0, 8, 9 or 0x0300000E, which look like paint/colour data and do not index into the list.

**Exosuit Personal Refiner:** sentinel key `GalacticAddress = 0`, `Position = (1,1,1,1)` in the personal buffer (see the verdict above).

**Portable refiner inside an owned base:**

- **How to match:**
  1. Take a base with the same `GalacticAddress`.
  2. Compute the object's world point as `base.Position + right*x + up*y + forward*z`, where up = `normalize(base.Position)` and forward = `base.Forward` orthogonalised.
  3. Compare the **direction** from the planet centre, not the distance. Base positions sit on a sphere about 10× larger than the keys: `|base.Position|` is 130,0xx where `|key|` is 13,0xx, and 64,6xx where it is 6,5xx, with similar ±100 m terrain spread. Euclidean distance never matches.
- **Result over all 26 saves:**
  - save3/4 "Cop Stop" `^BUILD_REFINER1` matched key 83 at 0.001 m (`MAINT_FUEL1` 96 + `STELLAR2` 123).
  - The other 4 owned `BUILD_REFINER1` and 1 owned `COOKER` had no key on that planet, or none within 20 m.
  - Owned biogenerators, planters and harvesters likewise had no entries. Base machines are therefore *not* persistently tracked in this list.
  - 0 of 440 refiners and cookers in other players' bases matched, as expected.

**Portable refiner outside a base:** not tied to anything. The save has no record of the placed object; only the key's position is stored, and nothing marks it as the player's.

**Freighter refiners:** some keys have `GalacticAddress == 0` and small coordinates (|p| 200–640, decks at y ≈ 201.7 / 212.8 / 225.5 / 245.3 / 256.4). They hold `MAINT_REFINER`-only containers with 1–4 items, which suggests freighter-interior refiners. A translation-voting search found no fixed offset between these keys and the `FreighterBase` object positions (`FRE_ROOM_REFINE` sits at e.g. (-32, 4, 19.5)). They cannot be tied to the current freighter.

**`RefinerBufferData`/`RefinerBufferKeys`:** despite the name, they mostly hold world-loot style containers (`SPACEGUNK*`, `EXOPOD_TECH*`, `LIFESUP_ROBO`, eggs plus alloys). Key `Location` values seen are 1–5 and 7. A few refiner signatures appear at Location 3 and 7 with local coordinates (save13–16). 0 of 165 Location-1 keys (6 saves tested) matched any base object by direction.

**Ghost entries:** `MaintenanceInteractions` also contains `(1,1,1,1)`-keyed refiner containers (up to 5 per save) with 2020–2023 timestamps. Identical ones are copied between the base and expedition contexts (e.g. index 76 and 778 in save15, save17 and save25). These are probably personal-refiner data from before the personal buffer existed. They are not live objects.

## Q4. How the order of `MaintenanceInteractions` maps to objects

- **By index to the key buffer**, as in Q3. The list does not map to objects by itself.
- **Not in chronological order** (saves, medium trust). The minimum timestamp per entry is non-decreasing for only 62–74% of adjacent keyed entries, whether read from index 0 or from `CurrentPos`. Populated entries are scattered across slots 0–999 with gaps.
  - Several saves show `CurrentPos = 0` while holding hundreds of keys, so `CurrentPos` is not a simple append cursor here.
  - The same entry keeps the same index across saves (for example index 76 in save15, save17 and save25), which fits a fixed 1,000-slot table where slots are reused.
  - The slot-selection rule was not found.
- **The personal buffer is append-ordered.** `StoredInteractions[9]` has 50 slots and `CurrentPos == len(PersonalMaintenanceInteractions)` in every save that has it.

## What a `refiner` container could show

This is only for entries already identified as refiners: the exosuit refiner, or a base portable refiner matched as in Q3.

Slot layout, from game data plus the saves:

- **Fuel-type refiners** (portable, exosuit, exocraft):
  - X0 = `MAINT_FUEL1`, whose `Amount` is the fuel level 0–100 (`MaxAmount` 100).
  - X1 = output, or the `MAINT_REFINER` placeholder when there is no output yet. `Amount == -1` appears on an output slot that exists but holds nothing yet.
  - X2+ = inputs.
  - Checked against the single-input recipes: in 24 of 24 unambiguous fuel + X1 + X2 entries the recipe result is at X1, never at X2; 7 more are ambiguous because the recipe is reversible. Example: save17 exosuit refiner, X1 `SPACEGUNK2` ×150 (Runaway Mould) and X2 `SPACEGUNK4` ×54 (Living Slime) = recipe `REFINERECIPE_54`.
  - A 2-slot container (fuel + one item at X1) cannot be told apart from an atmosphere or mineral harvester by content alone.
- **`MAINT_REFINER`-only refiners** (medium, large, freighter, corvette): the placeholder sits at X0 and items fill X1–X4. Which slot is the output was not established.

Fields:

| Field | Source | Confidence |
|---|---|---|
| input item + amount | slot X2+ | high for fuel-type refiners |
| output item + amount | slot X1 (non-placeholder) | high for fuel-type refiners |
| fuel % | `MAINT_FUEL1.Amount` | high |
| progress | output ÷ `DamageTimers[1]` (`DamageTimers[1]` equalled input+output in 31 of 68 entries and was 0 in 18; capped at 4095) | low; snapshot as of `LastUpdateTimestamp`, and the game advances refining on load |
| recipe | look up (input → output) in `nms_reality_gcrecipetable` | medium; reversible recipes are ambiguous |

## Method, for reproduction

- **Decoding:** the 26 saves were decoded read-only with `prototype/nms-core` (`nms_core.decode`, `extract.context`, bundled 6.11 key map). Walking a full save with the MBINCompiler 7.10 `mapping.json` left 0 unmapped keys. No maintenance store exists outside `PlayerStateData` (`MaintenanceInteractions`, `PersonalMaintenanceInteractions`, `RefinerBuffer*`, `RepairTechBuffer`, `StoredInteractions`).
- **Experiments:**
  - Flags bit-split versus contents and `DamageTimers`
  - key-buffer occupancy pairing
  - `SUIT_REFINER` presence versus the sentinel personal entry
  - angular matching of base objects to keys
  - translation voting for freighter keys
  - recipe matching for slot roles
- **Game data:** PAKs were copied to scratch before unpacking, and the game directory was only read.
