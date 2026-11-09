# What Marks a Built Storage Chest or Owned Exocraft, and What the Magic Chest Holds

Research for [#27](https://github.com/NafisAli/copotron-engine-r1/issues/27) (blocks the grilling ticket [#28](https://github.com/NafisAli/copotron-engine-r1/issues/28)). Date: 2026-11-10. This branch is never merged.

Trust tags used below:
- **[game data]**: highest trust. Unpacked from the local install (PAKs and `NMS.exe` dated 2026-11-06), converted with MBINCompiler 7.10.0.1.
- **[libMBIN]**: high trust. MBINCompiler `development` @ `59987b2` (2026-11-04).
- **[saves]**: measured on read-only copies of all 26 local saves (account `76561198101468572`).
- **[NMSE]**: medium trust. vectorcmdr/NMSE @ `e922f37` (2026-11-03), a shallow single-commit clone with no history.
- **[NomNom]**: low trust. zencq/NomNom @ `f3fa972` is changelog only; the source is closed.

"Inference" marks anything that is not read directly from a source.

## Answers

| Question | Answer | Confidence |
|---|---|---|
| Built storage chest | Chest *n* (`Chest{n+1}Inventory`) is built when one of the **player's** bases holds a `CONTAINER{n}`, `FRE_ROOM_STORE{n}` or legacy `S_CONTAINER{n}` object. The grid itself carries no signal: all ten grids are identical. | High for the mapping. Medium that "built" and "holds items" coincide in practice (they differ in 1 save pair). |
| Owned exocraft | `VehicleOwnership[i].Location != 0`. It equals the galactic address of that exocraft's geobay in every case. Tech, `PrimaryVehicle`, blueprints and the grid are not markers. | High (measured 18/18 positive and 151/151 negative, and NMSE uses the same test) |
| `ChestMagicInventory` | The inventory of the **Base Salvage Capsule** (`BASECAPSULE`), which stores matter recovered from a destroyed base. It is empty in all 26 saves. `ChestMagic2Inventory` is unknown (NMSE: "Freighter Refund (unused)") and also empty everywhere. | High for ChestMagic; low for ChestMagic2 |
| Index names | 0 Roamer, **1 Nomad**, 2 Colossus, 3 Pilgrim, **4 Dragonfly (unreleased)**, 5 Nautilon, 6 Minotaur | High (game data) |

**The v1 extractor on `feature/nms-save-engine` @ `4051054` gets index 1 and 4 wrong.** `implants/nms/nmslib/extract.py:32` has `["Roamer", "Bike", "Colossus", "Pilgrim", "Nomad", ...]`. Index 1 is the Nomad and index 4 is the Dragonfly. See [Effect on v1](#effect-on-v1-for-28).

## Q1. Can a built storage chest be told apart from an unbuilt one?

**Yes, but only through Base Parts, not through the grid.**

### The grids carry no signal

- **[libMBIN]** `GcPlayerStateData` has ten fixed fields `Chest1Inventory`…`Chest10Inventory` (`GcInventoryContainer`) plus `Chest1Layout`…`Chest10Layout` (`GcInventoryLayout`). They are always present. The game's `GcInventoryChoice` enum lists `Chest1`…`Chest10`, `ChestMagic` and `ChestMagic2` as separate inventories.
- **[saves]** In every save, all ten chest grids are identical in `Width`, `Height`, `ValidSlotIndices` count, `Class`, `StackSizeGroup` (`Chest`) and layout `Slots`. Only the era differs:

  | Saves | Grid | Unlocked slots |
  |---|---|---|
  | `save`–`save4` (version 4616–4628) | 3×3 | 5 |
  | `save9`–`save12` (4647/4648, plus `save10` = 7204) | 5×4 | 20 |
  | all later saves (4674+) | 10×6 | 50 |

  Capacity, unlocked slots and `NumSlotsFromTech` (always 0) cannot separate built from unbuilt chests.
- **[saves]** `GcInventoryContainer.Name` defaults to `"BLD_STORAGE_NAME"` (it is absent before 4647). In `save7`/`save8`, chests 0 and 1 are named `"Box 1"` and `"Box 2"`, and both are built. A custom name is a positive signal only: a built chest can keep the default name. **[game data]** confirms the Storage Room "may be renamed for ease of identification" (`BLD_FRE_ROOM_STORE_DESC`).

### Base Parts mark a built chest

**[game data]** `basebuildingobjectstable`, `nms_basepartproducts` and the English locale give these parts:

| Base Part | Name | Where | Limits |
|---|---|---|---|
| `CONTAINER0`…`CONTAINER9` | "Storage Container" (`BLD_STORAGE_NAME_L`), with icon `BUILDABLE.CONTAINER.<n>` | `BuildableOnPlanetBase` and `BuildableOnSpaceBase` true; `BuildableOnFreighter` false | `PlanetBaseLimit` 1, `CorvetteBaseLimit` 1, `CanPickUp` false |
| `FRE_ROOM_STORE0`…`FRE_ROOM_STORE9` | "Storage Room" | freighter | — |
| `S_CONTAINER0`…`S_CONTAINER9` | legacy freighter storage room | — | group `FREIGHT_LEGACY`; every `Buildable*` flag is false, so it can no longer be built |

The Storage Room description (`BLD_FRE_ROOM_STORE_DESC`) says: "Inventory capacity interfaces directly with planetary Storage Containers". So `FRE_ROOM_STORE{n}` and `CONTAINER{n}` open the same chest. There are only ten chest inventories while the limit is one `CONTAINER{n}` *per base*. **Inference:** every placed copy of a given *n* shares one inventory.

**Mapping: part number *n* ↔ `Chest{n+1}Inventory`.**
- **[saves]** Every chest that holds items has a matching part with the same *n* (table below).
- **[NMSE]** NMSE labels `Chest{i+1}Inventory` as "Storage Container *i*" (`UI/Panels/BasePanel.cs`).

### Which bases count as the player's

Filtering on `Owner.UID` is wrong in both directions:
- Legacy (4616) bases have no `BaseType` and an empty `Owner`, yet `save2`'s "Iorub Outpost" is the player's and holds the built `CONTAINER0`.
- The expedition freighter in `save21`/`save22` is owned by a placeholder (`XXXX-CSTN-…`, "Player1").
- Unowned `ExternalPlanetBase` entries are expedition template bases. For example, `save15`/`save16` hold one with `CONTAINER0`–`CONTAINER5` while every chest is empty.

**[saves]** Tally of `PersistentPlayerBases` across the 26 saves:

| `BaseType` | Owner | Count |
|---|---|---|
| `HomePlanetBase` | player | 44 |
| `FreighterBase` | player | 10 |
| `FreighterBase` | placeholder | 2 |
| `PlayerShipBase` | player | 4 |
| `ExternalPlanetBase` | other players | 1,034 |
| `ExternalPlanetBase` | empty | 144 |
| absent (legacy) | empty | 6 |

`ExternalPlanetBase` entries are other players' cached bases or expedition templates. **Rule:** count a base as the player's when `BaseType` is `HomePlanetBase`, `FreighterBase` or `PlayerShipBase`, or `BaseType` is absent (legacy). This rule fits every save. Loose `PlayerStateData.BaseBuildingObjects` entries don't matter for chests, because a chest cannot be built outside a base (`CONTAINER*` has `BuildableOnPlanet` false). No loose `CONTAINER*` appears in any save.

### Measured result

**[saves]** "Built" uses the rule above. "Holds items" is v1's current rule.

| Save pair | Built chests (part → base type) | Chests holding items |
|---|---|---|
| `save`, `save5`/`6`, `save9`–`12`, `13`/`14`, `15`/`16`, `19`–`22`, `25`/`26` | none | none |
| `save2` | 0 (`CONTAINER0`, legacy base) | 0 |
| `save3`/`save4` | 1, 2 (`HomePlanetBase`) | 1, 2 |
| `save7`/`save8` | 0, 1 (`HomePlanetBase`) | 0, 1 |
| `save17`/`save18` | 0 (`CONTAINER0` ×2 + `FRE_ROOM_STORE0`), 1 (`CONTAINER1` + `FRE_ROOM_STORE1`) | 0, 1 |
| **`save23`/`save24`** | **none (the player owns no base at all)** | **1: `F_ALL_RARE_S2`, `F_ODD_RARE_L1`, `F_ODD_RARE_XL`** |

- **Contents can outlive the part.** In `save23`/`save24`, Chest 1 holds 3 fish while nothing in the save builds a `CONTAINER1`.
  - Inference: the game keeps chest contents when the container (or its whole base) is removed, so rebuilding `CONTAINER1` would show them again. The save gives no record of the deletion.
- **No built-but-empty chest exists in the local saves.** The rule would detect one, but this could not be tested.

## Q2. Is exocraft ownership marked anywhere?

**Yes: `VehicleOwnership[i].Location` (a `ulong` galactic address) is non-zero exactly for exocraft the player has deployed.**

### Structure

**[libMBIN]** `GcPlayerStateData.VehicleOwnership` is `GcPlayerOwnershipData[7]` with `EnumType = GcVehicleType` (field index 166). The array is indexed by vehicle type, not by acquisition order.

`GcPlayerOwnershipData` has these fields: `Name`, `Resource`, `Inventory`, `Inventory_Cargo`, `Inventory_TechOnly`, `InventoryLayout`, `Location` (`ulong`), `Position` and `Direction` (`Vector4f`), and `VehicleCargo`. There is no flag field. `GcPlayerStateData.PrimaryVehicle` is a plain `int`.

### Measured: `Location` matches the geobay

**[saves]** Over all 169 `VehicleOwnership` entries in 26 saves:
- 18 entries (9 distinct, each in a duplicate save pair) have `Location != 0`.
- **Every one of them** equals the `GalacticAddress` of that exocraft's geobay, held either in a player base or as a loose `PlayerStateData.BaseBuildingObjects` entry.
- **Every** exocraft with a player geobay has `Location != 0`.
- There are 0 mismatches.

| Save pair | Deployed (`Location`) | Geobay found |
|---|---|---|
| `save7`/`8` | Roamer, Nomad, Colossus, Pilgrim @ `0x209E00FF958E2E`; Nautilon @ `0x422700FF955E2C` | `GARAGE_M`, `GARAGE_S`, `GARAGE_L`, `GARAGE_B` in "Iauehi Outpost" (same address); loose `GARAGE_SUB` (same address) |
| `save15`/`16` | Colossus @ `0x61C100039060B9` | loose `GARAGE_L` (same address) |
| `save17`/`18` | Minotaur @ `0x101200FE901FB0` | loose `GARAGE_MECH` (same address) |
| `save21`/`22` | Roamer @ `0x404800F808F6D2`, Pilgrim @ `0x200500F808F6D2` | `GARAGE_M`, `GARAGE_B` in two player bases (same addresses) |

- **[saves]** Every `Location == 0` entry (151 of 151) has `Position == (0,0,0)` and `Direction == (0,0,0,-1)`. Every deployed entry (18 of 18) has a real `Position`. These are a consistent secondary signal.
- **[saves]** Geobays in unowned `ExternalPlanetBase` expedition templates do **not** set `Location`. `save5`/`6` have `GARAGE_MECH` and `GARAGE_L`; `save13`/`14` have `GARAGE_S`, `GARAGE_M`, `GARAGE_B` and `GARAGE_L`. All of those exocraft have `Location == 0`. "Any geobay in any base" is therefore not a usable rule. `Location` is.
- **[NMSE]** `UI/Panels/ExocraftPanel.cs` sets `deployed = location != 0` and labels the result "Deployed" or "Not Deployed". Its "Undeploy" action writes `Location = 0`, `Position = 0` and `Direction = (0,0,0,-1)`. This independently matches the measurement.
- **[NomNom]** The changelog mentions an "Exocraft tab … showing whether one was already deployed" and "Exocraft unlock logic". The rule itself cannot be seen.

### Candidates that are *not* markers

- **Exocraft tech in the grid.** **[saves]** Every entry ships default tech whether deployed or not:
  - Roamer, Nomad, Pilgrim and Dragonfly: `VEHICLE_ENGINE` + `VEHICLE_BOOST`
  - Colossus: `VEHICLE_ENGINE` + `VEHICLE_LASER`
  - Nautilon: `SUB_ENGINE`
  - Minotaur: `MECH_ENGINE` + `MECH_BOOST` + `MECH_PROT`

  Extra tech appears only on deployed exocraft, but several deployed ones carry only the defaults (`save7` Nomad and Colossus, `save21` Roamer and Pilgrim). Extra tech is therefore a one-way hint.
- **Geobay or summoning-station Base Parts.** **[game data]** Each geobay scene references an entity carrying `GcVehicleGarageComponentData { Vehicle: GcVehicleType }`. The model scene is matched to its `*_PLACEMENT` scene by name:

  | Base Part | Name | Scene → garage entity | Vehicle type |
  |---|---|---|---|
  | `GARAGE_M` | Roamer Geobay | `vehiclegaragecustomiser` → `vehiclegarage/vehiclegarage.entity` | Buggy |
  | `GARAGE_S` | Nomad Geobay | `vehiclegaragesmall` → `vehiclegaragesmall.entity` | Bike |
  | `GARAGE_L` | Colossus Geobay | `vehiclegaragelarge` → `vehiclegaragelarge.entity` | Truck |
  | `GARAGE_B` | Pilgrim Geobay | `vehiclegaragebike` → `vehiclegaragebike/vehiclegarage.entity` | WheeledBike |
  | `GARAGE_SUB` | Nautilon Chamber | `vehiclegaragesubmarine` → `vehiclegaragesubmarine.entity` | Submarine |
  | `GARAGE_FLOAT` | Nautilon Platform | no placement scene | — |
  | `GARAGE_MECH` | Minotaur Geobay | `vehiclegaragemech` → `vehiclegaragemech.entity` | Mech |

  Every geobay has `RegionLimit 1`, is buildable on a planet outside a base, and cannot be picked up.
  - Geobays work as a cross-check, but only after the owner and base-type filtering above, and a geobay may sit loose in `BaseBuildingObjects`.
  - **`SUMMON_GARAGE` ("Exocraft Summoning Station") is not vehicle-specific.** It has `RegionLimit 1` and `CanPickUp true`, and none is placed in any local save.
- **Blueprints.** **[saves]** `KnownProducts` containing `GARAGE_*` or `SUMMON_GARAGE` means the recipe is known. `save` and `save2` know `GARAGE_M` with nothing deployed.
- **`PrimaryVehicle`.** **[saves]** It is 0 (Roamer) in every save with nothing deployed. Elsewhere it equals one deployed index (3, 2, 6, 3). It records the last-used exocraft, not ownership.
- **The grid.** **[saves]** All seven entries are allocated with full-size grids, and legacy saves have 3, 6 or 7 entries depending on era.

**Inference and open point:** in-game, an exocraft is "owned" once its geobay has been built, and from then on it can be summoned anywhere. `Location` records where the exocraft is currently deployed. No local save shows whether `Location` survives deleting the geobay. If it does not, a player could own an exocraft that the save no longer marks.

## Q3. What is `ChestMagicInventory`?

**The Base Salvage Capsule's storage.**

- **[saves]** Both `ChestMagicInventory` and `ChestMagic2Inventory`:
  - have `StackSizeGroup = BaseCapsule` in every save that records it, while all ten chests use `Chest`
  - use an 8×6 (legacy) or 10×6 grid with 48 valid slots and an empty `Name`
  - **hold 0 slots in all 26 saves**
- **[libMBIN]** `GcInventoryStackSizeGroup` defines `Chest` and `BaseCapsule` as separate groups. `GcInventoryChoice` lists `ChestMagic` and `ChestMagic2` next to `Chest1`…`Chest10`.
- **[game data]** Base Part `BASECAPSULE`:
  - Name: "Base Salvage Capsule" (`UI_BASE_CAPSULE_NAME_L`)
  - Subtitle: "Autonomous Storage Device"
  - Description: "A construction recovery device. This optional piece of base technology stores and preserves matter left over after the destruction of a previous base."
  - Build properties: group `BASE_TECH`/`TECHTEMINALS`, `RegionLimit` 1, `PlanetBaseLimit` 1, `CanPickUp` false
  - Its scene `basecapsule.scene` uses `DEFAULTROOM/ENTITIES/CHEST.ENTITY`, whose `GcSimpleInteractionComponentData.SimpleInteractionType` is **`BaseCapsule`** (a separate enum value from `Chest`).
- **[NMSE]** `Core/BaseLogic.cs` labels `ChestMagicInventory` "Base Salvage Capsule" and edits it with the `BaseCapsule` stack group. It labels `ChestMagic2Inventory` "Freighter Refund (unused)".
  - **[game data]** has no string tying ChestMagic2 to a freighter refund. The locale has only the generic `UI_REFUND_BASE` ("Refund this Base").
  - The **goatfungus** editor (1.21.0) only has key-map entries for these fields.
- **[saves]** The player never built a capsule. All 21 `BASECAPSULE` parts in the saves sit in other players' `ExternalPlanetBase` entries.

**Confidence.** ChestMagic = Base Salvage Capsule rests on three things: the measured `BaseCapsule` stack group, the game's `BaseCapsule` interaction on the capsule part, and NMSE's label. The final link, which interaction opens which inventory, is in the game binary and not in data, so it is inference.

ChestMagic2's purpose is **unknown**. Treat it as unused: it is empty everywhere, and NMSE calls it unused.

Suggested display name: "Base Salvage Capsule". Contents are leftovers from a demolished base, not normal storage.

## Q4. Names of exocraft indices 0, 1, 3 and 4

**[libMBIN]** `GcVehicleType.VehicleTypeEnum` order is `Buggy, Bike, Truck, WheeledBike, Hovercraft, Submarine, Mech`. Names come from **[game data]**:

| Index | Enum | Title (`VEHICLE_<TYPE>_TITLE_L`) | Summon string | Vehicle entity |
|---|---|---|---|---|
| 0 | Buggy | **Roamer** | `UI_SUMMON_BUGGY` "Summon Roamer Exocraft" | `vehicles/buggy` (`MED_BUGGY`) |
| 1 | Bike | **Nomad** | `UI_SUMMON_BIKE` "Summon Nomad Exocraft" | `vehicles/bike` |
| 2 | Truck | Colossus | `UI_SUMMON_TRUCK` | `vehicles/rover` (carries the exocraft refiner) |
| 3 | WheeledBike | **Pilgrim** | `UI_SUMMON_WHEELEDBIKE` "Summon Pilgrim Exocraft" | `vehicles/wheeledbike` |
| 4 | Hovercraft | **Dragonfly** | `UI_SUMMON_HOVERSHIP` "Summon Dragonfly Exocraft" | `vehicles/hover/hovercraft` |
| 5 | Submarine | Nautilon | `UI_SUMMON_SUBMARINE` | `vehicles/submarine` |
| 6 | Mech | Minotaur | `UI_SUMMON_MECH` "Summon Minotaur Power Suit" | `vehicles/mech_suit` |

- The geobay components agree: the Nomad Geobay (`GARAGE_S`, `vehiclegaragesmall.entity`) is `Bike`, and the Pilgrim Geobay is `WheeledBike`.
- **The Dragonfly (index 4) is unreleased.** The locale has "Dragonfly Geobay" (`BLD_GARAGE_H_*`) and a `vehiclegaragehover` entity exists, but `basebuildingobjectstable` has no `GARAGE_H`, so it cannot be built. It is never deployed in any save.
- **[NMSE]** `Core/ExocraftLogic.cs` agrees: Roamer 0, Nomad 1, Colossus 2, Pilgrim 3, Nautilon 5, Minotaur 6, with 4 skipped.
- The ticket's list (Roamer, Nomad, Colossus, Pilgrim, ?, Nautilon, Minotaur) was right. The `EXOCRAFT` constant in `extract.py` is not.

## Effect on v1 (for #28)

**[saves]** The v1 extractor (`feature/nms-save-engine` @ `4051054`) was run on all 26 saves.

**Exocraft: v1 shows phantoms and misses deployed exocraft.**
- In all 8 legacy saves (`save`–`save4`, `save9`–`save12`), the default tech sits in the *general* grid (the tech grid is 0×0). The "non-tech grid holds items" rule therefore shows 3–7 exocraft per save, and **none of them is deployed**.
- It misses deployed exocraft whose cargo is empty:
  - `save7`/`8`: Roamer, Nomad, Colossus (it shows only Pilgrim and Nautilon)
  - `save21`/`22`: Roamer, Pilgrim (it shows nothing)
- **The `Location != 0` rule gives exactly the deployed set in all 26 saves.**

**Exocraft labels are wrong at index 1 and 4.**
- v1 labels index 1 "Bike" when it is the Nomad.
- v1 labels index 4 "Nomad" when it is the Dragonfly. In `save3` and `save9`–`12`, v1 shows the unreleased Dragonfly under the name "Nomad".

**Storage: "holds items" and "built" agree everywhere except `save23`/`24`.** There, Chest 1 holds 3 fish with no container built. A "built" rule would hide items the player still owns, and "holds items" shows them under a chest that isn't on any base.

**Magic chest: v1 never shows it.** It is empty in every save. If it is ever shown, call it "Base Salvage Capsule". Hide `ChestMagic2`, or keep it raw.

## Method, for reproduction

- **Saves.**
  - All 26 `save*.hg` (and their `mf_*` files) were copied from `%APPDATA%/HelloGames/NMS/st_76561198101468572/` to scratch.
  - They were decoded read-only with `implants/nms/nmslib` from `origin/feature/nms-save-engine` (extracted via `git archive`; `lz4` via `uv run --with lz4`).
  - Each save has one context: legacy top-level, `BaseContext` (Main) or `ExpeditionContext` (Season). None has both.
- **Game data.**
  - Tables, entities and locale were read from the local install `E:/SteamLibrary/.../GAMEDATA/PCBANKS`, using hgpaktool 1.1.3 (glob filters, list mode) and MBINCompiler 7.10.0.1.
  - Files used:
    - `basebuildingobjectstable`
    - `nms_basepartproducts`
    - `nms_loc*_english` and `nms_update3_english`
    - `vehicles/*/entities/*.entity`
    - `buildableparts/tech/vehiclegarage*/entities/*.entity`
    - `buildableparts/containers/container_0.scene`
    - `buildableparts/basecapsule.scene`
    - `buildableparts/defaultroom/entities/chest.entity`
- **libMBIN.** `GcPlayerStateData`, `GcPlayerOwnershipData`, `GcVehicleType`, `GcVehicleGarageComponentData`, `GcPersistentBase`, `GcPersistentBaseEntry`, `GcPersistentBBObjectData`, `GcInventoryContainer`, `GcInventoryChoice`, `GcInventoryStackSizeGroup`, `GcSimpleInteractionComponentData`, `GcInteractionType`.
- **Experiments:**
  - Per-chest grid fields across all saves
  - Chest index against `CONTAINER*`, `FRE_ROOM_STORE*` and `S_CONTAINER*` parts by base type and owner
  - `BaseType` × owner tally
  - `VehicleOwnership.Location` against geobay `GalacticAddress` (base-level for `Objects`, object-level for `BaseBuildingObjects`)
  - `Position`/`Direction` defaults
  - Default tech per index
  - Magic-chest contents and stack groups
  - v1 `extract.build` output per save
- **Not consulted:** community wikis. The primary sources were enough.

## Open questions

- Does `Location` survive deleting a geobay? This needs a dogfood save: build a geobay, deploy, delete, then save.
- Does deleting a Storage Container keep its contents? `save23`/`24` suggests yes, but it is a single observation without a recorded deletion.
- What is `ChestMagic2Inventory`? Nothing primary documents it.
