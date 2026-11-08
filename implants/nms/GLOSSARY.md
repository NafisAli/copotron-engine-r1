# No Man's Sky Implant

The vocabulary of the world the NMS Implant couples the brain to: a player's save, what they carry, and where things are in the universe. Copotron's own terms (Implant, Insertion, Implant Instructions) live in the control plane's glossary.

## Saves

**Save**:
One snapshot of a player's game, as the game wrote it to disk. The Implant only ever reads it.
_Avoid_: Game file, Profile, World

**Save Slot**:
One of the numbered save positions the game offers, holding a manual save and an autosave; the newer of the two is the slot's current Save.
_Avoid_: Slot (alone), Save file number

**Account**:
The platform identity a Save belongs to (a Steam user or a GOG install); one machine may hold several.
_Avoid_: Profile, User, Player

**Active Context**:
Which game a Save is currently in: the main game or an expedition. Each keeps its own location, wallet, inventory and bases.
_Avoid_: Mode, Season, Playthrough

**Game Mode**:
The difficulty preset a Save is played under, such as Normal, Survival or Permadeath.
_Avoid_: Difficulty, Context

## Inventory

**Inventory**:
Everything the player holds, across every Container in the Save.
_Avoid_: Stash, Cargo, Items

**Container**:
One grid of Inventory Slots with a single owner (the exosuit, a ship, a multi-tool, the freighter, a storage chest, an exocraft, or a single-purpose store such as the Grave). One owner may have several, kept apart as general, cargo and technology grids.
_Avoid_: Inventory, Bag, Chest (for anything but storage chests)

**Category**:
A named group of Containers that a query can target, such as suit, ship, storage or grave.
_Avoid_: Type, Kind, Section

**Inventory Slot**:
One cell of a Container, holding one stack of an item or one installed technology.
_Avoid_: Slot (alone), Cell

**Capacity**:
The number of Inventory Slots a Container currently has unlocked, not the size of its full grid.
_Avoid_: Size, Max slots

**At Cap**:
A stack holding the most of its item the slot allows; **Near Cap** is a stack at nine tenths of that or more.
_Avoid_: Full, Maxed

**Requisition Check**:
A test of whether the Inventory holds at least a stated amount of each named item, counted across every Container.
_Avoid_: Have-check, Shopping list, Shortage report

**Item Catalog**:
The bundled reference that names items from their game identifiers. An identifier it does not know is shown as is, never given a guessed name.
_Avoid_: Item database, Dictionary, Translations

## The Universe

**Address**:
A point in the universe: a Galaxy, a Region, a Star System within it, and a planet within that.
_Avoid_: Coordinates, Location (alone), Position

**Portal Glyphs**:
The twelve-symbol form of an Address that the game's portals dial; it carries the planet but not the Galaxy.
_Avoid_: Portal code, Glyph code, Portal address

**Signal Booster Code**:
The four-part form of an Address that the game's signal booster shows; it carries no planet and no Galaxy.
_Avoid_: Booster coordinates, Galactic coordinates

**Galaxy**:
One of the 256 separate universes a player travels between; distances are never measured across two Galaxies.
_Avoid_: Reality, Dimension

**Region**:
The cube of space a Star System sits in; Star Systems in the same Region are a short warp apart.
_Avoid_: Voxel, Sector, Cluster

**Star System**:
One star and its planets, identified by its Galaxy, its Region and its index within that Region.
_Avoid_: Solar System, System (alone, when ambiguous), Sector

**Discovery**:
A record that someone first found a Star System, planet, creature, plant or mineral, carrying who found it and any name they uploaded.
_Avoid_: Scan, Finding, Upload

## Ownership

**Mine**:
Owned or discovered by the player's own Account.
_Avoid_: Owned, Personal, Local

**Base**:
A structure the game persists at an Address, such as a planetary base, the freighter base or a corvette.
_Avoid_: Settlement, Outpost, Home (except the home planet base)

**Visited Base**:
A Base owned by another player that the Save keeps a copy of because the player came near it.
_Avoid_: Foreign base, Other base, Community base
