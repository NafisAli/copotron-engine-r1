# Source and Trigger for Item Catalog and Key Mapping Refreshes

Research for [#19](https://github.com/NafisAli/copotron-engine-r1/issues/19) (parent decision [#20](https://github.com/NafisAli/copotron-engine-r1/issues/20)). Date: 2026-11-09. This branch is never merged.

Trust levels: **high** = upstream source code, release metadata or game files read directly; **measured** = a local run on copies of the game PAKs and saves (reproducible, but one machine); **medium** = upstream data whose meaning is inferred; **low** = third-party mirror.

## Recommendations

1. **Refresh source.** *Catalog:* re-run the dev-time PAK build (`tools/build_catalog.py`: copied PAKs → hgpaktool → MBINCompiler → English join) against the local install. Nothing else is current: the npm package stopped at game 6.01 in August 2025. *Key mapping:* take the `mapping.json` asset from the **same pinned MBINCompiler release** used for the catalog. Lay it over the existing merged mapping without dropping any key, so the legacy fill and savewizard fixups survive. MBINCompiler's CI generates the file from libMBIN on every tagged release.
2. **Do not extract `basebuildingobjectstable`.** Its 2,340 entries carry no name field. The names of base parts live in **`nms_basepartproducts.mbin`**, which uses the same `GcProductTable` template as the product table, so the existing parser reads it. Add that one table to the build. The catalog grows from 2,930 to 4,882 names. It names 49 more distinct slot ids (124 of the 292 unnamed slot occurrences), and base-object coverage goes from 2.1% to 99.9%.
3. **MBINCompiler fetch.** Pin one release **tag plus SHA-256** in the build tool. Download `https://github.com/monkeyman192/MBINCompiler/releases/download/<tag>/{MBINCompiler.exe,mapping.json,report.json}` and check each file against the pinned hash, which equals the GitHub asset `digest`. To choose the tag, list `/releases` and not `/releases/latest`: CI publishes every release as a prerelease, so `latest` lags. `report.json` `version` is the **Steam BuildID** the release was tested on, and you compare it with `buildid` in `appmanifest_275850.acf`. Run `convert` **without `-q`** and refuse to write if any file the build reads triggers `File not recognized`. A mismatched compiler exits 0, and `-q` hides the warning.
4. **Trigger: compare the save's version with the snapshot's.** The snapshot header records the save base version (`Version % 512`, here 138) of the newest local save at build time. When the implant opens a save with a higher base version, it adds a one-line "snapshot older than this save, run the refresh" note. The refresh itself stays a manual dev-time command. In local data, every 2026 save-version bump came with new save keys that only the next MBINCompiler mapping covered.

---

## Part 1: Refresh source for each snapshot

### Item catalog: re-run the PAK build

- **The build works on today's install and is cheap (measured).** Setup: copies of `NMSARC.MetadataEtc.pak` and `NMSARC.Precache.pak` from the install (build 26463810, PAKs dated 2026-11-05/06), unpacked with hgpaktool 1.1.3 using the filters `*REALITY/TABLES/*.mbin` and `*LANGUAGE/nms_*_english.mbin`.
  - Unpacking 64 files took 0.5 s.
  - Converting them with MBINCompiler v7.14.0-pre1 took 6.3 s.
  - The prototype's four tables give **2,930 items** from 85,083 English locale keys. This is identical to the committed snapshot on `prototype/nms-core` @ `12e92d8` (`implants/nms/nms_core/data/items.json`, header `"mbincompiler": "7.10.0.1"`, `"count": 2930`).
- **The npm package is stale (high).** The npm registry shows `assistantapps-nomanssky-info` latest = `6.1.4990`, published 2025-08-28. No version has been published in the 14 months since. PR #18's snapshot header carries `GameVersion: "6.01"`, `GameBuildNumber: 19773093` (`feature/nms-save-engine` @ `4051054`, `implants/nms/nmslib/data/items.json`).
  - The publisher has gone quiet: the AssistantNMS org's `App` repo was last pushed 2025-10-08 and `WebApi` 2024-07-04 (GitHub API).
  - Since 6.01 the game has shipped 6.1x through 7.1x (MBINCompiler tags v6.10 … v7.14).
  - #20 measured npm at 79.8% slot coverage vs 95.2% for the PAK build.
- **hgpaktool does not track game versions (high).** It is PyPI `hgpaktool` (MIT, `monkeyman192/HGPAKtool`). The latest release, 1.1.3, dates from 2026-02-16, and it still unpacks the 2026-11 PAKs (measured). It only handles the PAK container (ZSTD on Windows), not MBIN templates. Pin `hgpaktool==1.1.3` in the script's inline metadata (it currently says `>=1.1`).

### Key mapping: the MBINCompiler release `mapping.json`

- **Where it comes from (high).** In `.github/workflows/pipeline.yml` on MBINCompiler `development` @ `59987b2` (= tag v7.14.0-pre1), the `save_mapping` job builds `SaveFileMapping` and runs it on every push.
  - The `release` job runs only on tags. It uploads that `mapping.json` with the binaries and `report.json` as release assets, with `prerelease: true`.
  - `SaveFileMapping/Program.cs` hashes every field name of the libMBIN `GcPlayerStateData`, `GcPlayerCommonStateData`, `GcGalaxyWaypoint` and `GcUserSettingsData` classes, plus a fixed list of root keys (`Version`, `Platform`, `ActiveContext`, …). It uses SpookyHash, 3 chars, as in AndASM's method.
  - So the mapping is a pure function of the libMBIN version, and the release that matches the game build also carries the matching mapping.
- **How fast it appears (high, release and news timestamps).** The table compares the HG Steam announcement time (`ISteamNews/GetNewsForApp`, appid 275850) with the first MBINCompiler release of the matching minor version:

  | Update | Announcement (UTC) | First release | Lag |
  |---|---|---|---|
  | Worlds Part I 5.0 | 2024-07-17 13:22 | v5.01.0-pre1 2024-07-19 13:49 | ~48 h |
  | Aquarius 5.10 | 2024-09-04 13:17 | v5.10.0-pre1 14:20 | 1 h |
  | The Cursed 5.20 | 2024-10-23 13:03 | v5.20.0-pre1 14:08 | 1 h |
  | Worlds Part II 5.50 | 2025-01-29 15:46 | v5.51.0-pre1 01-30 02:36 | 11 h |
  | Relics 5.60 | 2025-03-26 14:12 | v5.61.0-pre1 21:48 | 7.5 h |
  | Beacon 5.70 | 2025-06-04 13:15 | v5.71.0-pre1 06-05 07:58 | 19 h |
  | Voyagers 6.0 | 2025-08-27 13:06 | v6.01.0-pre1 08-28 01:34 | 12.5 h |
  | Breach 6.10 | 2025-10-22 12:58 | v6.10.0-pre1 11:20 | −1.6 h |
  | Remnant 6.20 | 2026-02-11 14:03 | v6.20.0-pre1 02-12 02:39 | 12.6 h |
  | Xeno Arena 6.30 | 2026-04-08 13:02 | v6.30.0-pre1 12:19 | −0.7 h |
  | The Swarm 6.40 | 2026-05-27 13:02 | v6.40.0-pre1 22:36 | 9.6 h |
  | Cosmos 7.0 | 2026-09-09 13:00 | v7.00.0-pre1 14:22 | 1.4 h |
  | Forsaken 7.10 | 2026-10-28 14:05 | v7.10.0-pre1 20:56 | 6.9 h |

  Every major update since mid-2024 has a release within two days, usually the same day. Two releases even came out before the announcement post.
- **The maintainers track every Steam build, experimental ones included (high).** `monkeyman192/MBINCompiler-test-data` publishes one release per game build, titled "MBINCompiler test data for NMS Steam BuildID N". There were 21 such builds between 2026-09-09 and 2026-11-03.
  - In the same period there were 13 MBINCompiler releases. Builds whose templates did not change (e.g. 26308211, 26331461) got test data but no new compiler.
  - Build 26413549 (test data 2026-11-03 21:52) is newer than the public branch's 26386568. The public build id comes from api.steamcmd.net, **low** trust.
- **The mapping only ever grows (high).** I diffed the `mapping.json` of 16 releases from v6.01 to v7.14:

  | Release | Keys | Added since previous |
  |---|---|---|
  | v6.01 | 1,321 | — |
  | v6.11 | 1,337 | +16 |
  | v6.20 | 1,359 | +22 |
  | v6.30 | 1,375 | +16 |
  | v6.33 | 1,379 | +4 |
  | v6.40 | 1,415 | +37 |
  | v6.44 | 1,416 | +1 |
  | v6.45 | 1,416 | +0 |
  | v7.00 | 1,462 | +46 |
  | v7.01 | 1,462 | +0 |
  | v7.02 | 1,462 | +0 |
  | v7.03.2 | 1,463 | +1 |
  | v7.04.1 | 1,464 | +1 |
  | v7.07 | 1,467 | +3 |
  | v7.10 | 1,496 | +29 |
  | v7.14 | 1,496 | +0 |

  - No key ever changed its readable name.
  - One key was removed: `bQN` → `ActiveSpaceBattleLevel`, gone in v6.40.
  - So a refresh should **lay the new release over the existing merged mapping** (new wins, nothing dropped), not replace it.
- **The raw release mapping is not enough on its own (measured).** Each column below is a mapping; each cell counts the distinct obfuscated keys left unmapped across all keys in that save:

  | Save `Version` | 6.11 merged (PR #18) | raw v7.00 | raw v7.07 | raw v7.10 / v7.14 | merged ∪ v7.14 |
  |---|---|---|---|---|---|
  | 4628–4686 (2018–2024) | 0 | 2–9 | 2–9 | 2–9 | 0 |
  | 4719 (Feb 2026) | 18 | 1 | 1 | 1 | 0 |
  | 4733 (Jun 2026) | 76 | 0 | 0 | 0 | 0 |
  | 4738 (Sep 2026) | 71–107 | 0 | 0 | 0 | 0 |
  | 4746 (Nov 2026) | **92** | 21 | 21 | **0** | 0 |

  - Old saves still need the legacy layer. New saves need the newest release.
  - The 6.11 merged column is `feature/nms-save-engine:implants/nms/nmslib/data/mapping.json`: libMBIN 6.11.0.1, keys = MBINCompiler + legacy fill-gaps, fixups = savewizard `{"MultiTools": "Multitools"}`.
  - The 92 for version 4746 reproduces #20's figure.

### Part 1: rejected alternatives

- **npm `assistantapps-nomanssky-info` as the refresh source, or as a fallback.** It stopped at 6.01 (2025-08-28) and covers fewer slots. A fallback only helps a machine without the game, and the snapshot is committed, so no such machine needs to build it.
- **NMSE's committed DB (`vectorcmdr/NMSE` `Resources/json/*.json`, "Update DB to 7.10" 2026-10-29).** It is current, but secondary: the same pipeline run by someone else. It is also AGPL-3.0 (GitHub license API), which we should not vendor into the engine.
- **Generating `mapping.json` ourselves.** That needs a .NET build of `SaveFileMapping` against libMBIN source and gives byte-for-byte the release asset.
- **NMSE's `Resources/map/mapping.json`.** It is a hand-copied release asset (commit "Update DB to 7.10", `libMBIN_version 7.10.0.1`). Taking it adds a hop and a lag.
- **goatfungus NMSSaveEditor.** The repo was last pushed 2026-06-05, before 7.0.

---

## Part 2: Whether to extract `basebuildingobjectstable`

**Answer: no. Extract `nms_basepartproducts.mbin` instead.**

- **The table has ids but no names (measured, game data).** `metadata/reality/tables/basebuildingobjectstable.mbin` converts to `cGcBaseBuildingTable` with `Objects: List<GcBaseBuildingEntry>`.
  - Each entry carries `ID`, placement flags (`BuildableOnPlanetBase`, `BuildableOnFreighter`, `CanPickUp`, …), `Groups`, `LinkGridData` and `IconOverrideProductID`, but **no name or locale key**.
  - Across its 2,340 entries:
    - 0 have a non-empty `IconOverrideProductID`.
    - 0 ids are themselves locale keys.
    - 367 ids are already named by the prototype's product, substance and technology tables.
    - **1,880 are named by `nms_basepartproducts`.**
  - NMSE takes the same route (high, `vectorcmdr/NMSE` @ `e922f37`, `NMSE.Extractor/Data/Parsers.cs`). `ParseBuildings` names an entry via `Translate(buildingId, …)` and needs `IconOverrideProductID` to find an icon. `ParseBaseParts` simply runs `ParseProducts` over `nms_basepartproducts`.
- **`nms_basepartproducts` reads with the existing parser (measured).** Its MBIN header has the same template as `nms_reality_gcproducttable`: name hash `06EDC332`, GUID `D648571CB22CFD4B`.
  - The prototype's `parse()` join (`ID` → `NameLower`/`Name` → English) gives **1,952 named rows**.
  - None of them overlap the existing 2,930 items.
  - 72 of them are not in `basebuildingobjectstable`.
  - Combined catalog: **4,882 items**. Expect roughly 1.7× the prototype's 210 KB.
- **Ids from that table do show up unnamed, in inventories and much more in base objects (measured, all 26 local saves, mapping = 6.11 merged ∪ v7.14).** The slot denominator here is every `Slots` list in the save, which is wider than #20's six categories; the base-object denominator is every `PersistentPlayerBases[].Objects[].ObjectID`.

  | | Occurrences | Prototype names | + `nms_basepartproducts` | Still unnamed |
  |---|---|---|---|---|
  | Inventory slot ids | 25,521 (646 distinct) | 25,229 (98.9%) | 25,353 (99.3%) | 168 |
  | Base object ids | 103,218 (971 distinct) | 2,146 (2.1%) | 103,160 (99.9%) | 58 |

  - In slots, the base parts it adds are 49 distinct ids, e.g. `BUILD_REFINER1`, `BASE_FLAG`, `BP_ANALYSER`, `BUILDSIGNAL`, `B_STR_*`.
  - Slot ids left after adding it:
    - 16 distinct (39 occurrences) are 2018-era ids that `legacyitemtable.mbin` converts, e.g. `COM1`→`LAND1` "Ferrite Dust", `TECH1`→`YELLOW2` "Copper".
    - 4 are in `nms_modularcustomisationproducts`.
    - 1 is `B_MAG_1X1`, a `basebuildingobjectstable` id with no name anywhere.
    - 55 are pre-NEXT upgrade ids or corrupt bytes.
  - In base objects, 760 distinct ids (101,014 occurrences) are added, e.g. `U_POWERLINE`, `T_FLOOR`, `U_SOLAR_S`. The 4 left (`FREIGHTER_CORE`, `U_PARAGON`, `AIRLCKCONNECTOR`, `BRIDGECONNECTOR`) are `basebuildingobjectstable` ids with no name in any table.
- **The names come from the same language tables.** The `nms_*_english` set is unchanged and has 85,083 keys. No extra locale file is needed.

### Part 2: rejected alternatives

- **Extracting `basebuildingobjectstable` for names.** It adds no names of its own. It is only worth extracting later for placement or ownership metadata (planet vs freighter, `CanPickUp`). That is a separate feature, not catalog scope.

---

## Part 3: Fetching an MBINCompiler that matches the game

### How MBINCompiler versions map to game versions

- **Naming (high).** `libMBIN/Source/Version.cs` @ `59987b2`: `VERSION_STRING = "7.14.0.1"`. The comment reads: "The Major and Minor version numbers should match the NMS version that is supported", the 3rd number is the libMBIN release and the 4th the prerelease.
  - `GetString()` renders `7.14.0-pre1`, and the release job refuses to publish unless `MBINCompiler.exe version` equals the tag.
  - So tag `vX.YY.R-preN` means game X.YY. Every tag so far carries a `-pre` suffix, including `v7.03.2-pre2` and `v7.04.1-pre3`.
- **The exact build (high).** Each release's `report.json` has `version` = the Steam BuildID of the test data it passed. `tests/utils.py` downloads `MBINCompiler-test-data` `/releases/latest`, and `generate_report` reads its `.version` file. For the 7.x line:

  | Tag | Tested Steam BuildID |
  |---|---|
  | v7.00.0-pre1 | 25208017 |
  | v7.01.0-pre1 | 25215278 |
  | v7.02.0-pre1 / pre2 | 25254115 / 25308586 |
  | v7.03.2-pre1 / pre2 | 25372592 / 25407754 |
  | v7.04.0-pre1 | 25441199 |
  | v7.04.1-pre1 / pre2 / pre3 | 25484636 / 25509176 / 25511792 |
  | v7.07.0-pre1 | 25800958 |
  | v7.10.0-pre1 | 26271400 |
  | v7.14.0-pre1 | 26413549 |

  All 13 releases report 463/469 tests passing.
- **The MBIN header carries no game version (high + measured).** `libMBIN/Source/MBIN/MBINHeader.cs`: magic `0xCCCCCCCCCCCCCCCC`, `MbinVersion` must be `3300`, `TemplateGUID` at 0x10 is per template, and `Timestamp` at 0x18 is "empty, the actual timestamp, or all \xFF's" for vanilla files.
  - All 64 extracted files have `mbinver=3300`, `hdrver=0`, `ts=0`.
  - **The real compatibility check is `TemplateGUID`.** `Commands/Convert.cs` compares `mbin.Header.TemplateGUID` with the template's `NMSAttribute.GUID`. On a mismatch it only *warns*: "File not recognized. You may need to use an older (or newer) version of MBINCompiler". It still deserializes and returns success unless an exception is thrown.

### How to read the installed game's version

- **Steam manifest (high, local file).** `E:\SteamLibrary\steamapps\appmanifest_275850.acf` has:
  - `"buildid" "26463810"` and `"TargetBuildID" "26463810"`
  - `"LastUpdated" "1793935826"` (2026-11-06 03:30 UTC)
  - `UserConfig.BetaKey "experimental"`, so **this machine runs the experimental branch**. That branch's `timeupdated` is 2026-11-05 16:53 UTC.
  - Find the library through Steam's `libraryfolders.vdf`. NMSE gets the Steam root from registry `SOFTWARE\Wow6432Node\Valve\Steam\InstallPath` (`NMSE.Extractor/Util/SteamLocator.cs`).
- **What does not work (measured).**
  - `NMS.exe`'s version resource says `FileVersion 185034` and `ProductVersion 53962.0.0.0`. Neither is the X.YY patch number.
  - None of the 65,742 entries in the three listed PAKs (`MetadataEtc`, `Precache`, `globals`) is a version file.
  - MBIN header timestamps are 0.
- **The installed build is newer than the newest MBINCompiler, and nothing broke (measured).** Build 26463810 is newer than v7.14's 26413549. Still:
  - v7.10.0-pre1 and v7.14.0-pre1 both convert all 64 table and language files with **0 GUID warnings and exit 0**.
  - Their MXML is **identical** apart from the version comment.
  - Templates only change on some builds. The GUID gate, not the BuildID, decides whether a compiler fits.

### Mismatched compilers fail silently (measured)

The same 14 files were run through two older compilers: the prototype's four tables, `nms_basepartproducts` and nine English locale files.

| Compiler (tested build) | `-q` output | Without `-q` | Exit | Catalog vs v7.14 |
|---|---|---|---|---|
| v7.07.0-pre1 (25800958, pre-Forsaken) | nothing | GUID warnings on substance, product and basepartproducts | 0 | same 4,882 names. The substance MXML differs in 544 diff lines (`ScanIconType` misread, `OnlyFoundAtSpacePOIs` missing) |
| v6.11.0-pre1 (2025) | nothing | GUID warnings on all 14 files | 0 | **113 items missing (3.9%), 1 renamed**. This passes the prototype's "refuse if >10% shrink" guard |

Over the full 64-file set, both old compilers hit exceptions on base-building and combat tables. Each then exited 1 having converted only 17 of 64 files. So the prototype's narrow filter set is exactly the case that "succeeds" wrongly. **The build must run without `-q` and treat `File not recognized` as fatal.**

### A pinnable fetch

- **URLs (high, GitHub releases API).**
  - Listing: `GET https://api.github.com/repos/monkeyman192/MBINCompiler/releases`
  - Assets: `https://github.com/monkeyman192/MBINCompiler/releases/download/<tag>/<asset>`
  - Asset names on 7.x: `MBINCompiler.exe` (net8, Windows), `MBINCompiler-dotnet10.exe`, `MBINCompiler-linux`, `MBINCompiler-linux-dotnet10`, `MBINCompiler-macOS.zip`, `libMBIN*.dll/.so`, `mapping.json`, `report.json`.
  - This machine has .NET 8.0.10 and no .NET 10 runtime, so use `MBINCompiler.exe`.
- **Checksums (high).** The releases API now exposes `assets[].digest` = `sha256:…`. It matched a local `sha256sum` for every file downloaded:

  | Tag | Asset | SHA-256 |
  |---|---|---|
  | v7.14.0-pre1 | `MBINCompiler.exe` | `d63e70ad5749b4c2294ba6185385986c47daeed17129507e37233da8a12ade6d` |
  | v7.14.0-pre1 | `mapping.json` | `8ce1d93707edd694e7430f767bf0c97cc89e0bc839e6cf2375898c19e3ba98f3` |
  | v7.14.0-pre1 | `report.json` | `b2f8ad7e468c7ca1573ff4715df740a9b45ba6fd856ccfa2e3b47c9144ded903` |
  | v7.10.0-pre1 | `MBINCompiler.exe` | `035c5645753be3cced709b9f1bdcd73d25ea9c5e2f06a438dba45a38d11f9b41` |
  | v7.10.0-pre1 | `mapping.json` | `677ce606579831996be4c858ac4193959190958604c4f460eb560dc1e1d6c626` |

  The v7.07 and v6.11 executables matched their API digests too.
- **Do not use `/releases/latest` (high).** CI creates every release with `prerelease: true`. A maintainer later clears the flag by hand: today v7.14.0-pre1 is still `prerelease: true` and every older release is `false`. So `/releases/latest` currently returns **v7.10.0-pre1**. NMSE's `ExtractorConfig.cs` uses `/releases/latest/download/…` and so lags by one release.
- **Selection rule.**
  1. List the releases, ignoring the prerelease flag, and take the newest tag.
  2. Fetch its `report.json` and record `version` (the tested BuildID) next to the installed `buildid`.
  3. Pin tag + SHA-256 in `tools/build_catalog.py`, the same pin for `mapping.json`.
  4. Run the GUID gate.
- **When the game is newer than the latest MBINCompiler.** On an update day this lasts 0–48 h (table above). Run anyway: the GUID gate either passes, as on 26463810 today, or refuses to write. When it refuses, wait for the next release. Never fall back to an older tag.

### Part 3: rejected alternatives

- **"Always download latest" (NMSE's approach).** It is not reproducible and lags because of the prerelease flag.
- **Matching on the X.YY game version.** The install does not expose X.YY anywhere readable. The BuildID plus the GUID gate is exact.
- **Building MBINCompiler from source.** It needs a .NET SDK and gives nothing over the CI-built, digest-checked assets.

---

## Part 4: Refresh trigger

### What version a save carries

- **Measured, all 26 saves, decoded with 6.11 merged ∪ v7.14.** The only game-version signal is the root `Version` (obfuscated `F2P`), next to `Platform: "Win|Final"`.
  - Everything else named `*Version` is local: inventory `Version` 0/1, `MissionVersion` 40/41, base `BaseVersion` 8.
  - There is no BuildID and no X.YY string anywhere in the tree (key-name scan for `version|build|patch` on save17 and save25).
- **`Version` encodes base version + game mode (high).** libNOM.io @ `652aabb`, `Meta/BaseVersion.cs`: `BaseVersion = SaveVersion − (GameMode + Season·128)·512`, with `Constants.OFFSET_GAMEMODE = 512`. `Meta/GameVersion.cs` maps base-version ranges to releases (e.g. `>= 4189 → Voyagers // 6.00`).
  - Every offset is a multiple of 512, so `Version % 512` is the base version mod 512. That holds whatever the game mode or season.
  - It identifies the base version uniquely while that stays in 4096–4607. It is 4234 today and rose by 41 in the last 14 months.
- **Each save-version bump required a newer mapping (measured).** The table shows the earliest release whose `mapping.json` ∪ the legacy-merged base leaves 0 keys unmapped:

  | Save `Version` | Base | Written | Earliest sufficient mapping |
  |---|---|---|---|
  | 4628–4705 | ≤4193 | 2018 – Sep 2025 | v6.01 |
  | 4719 | 4207 | Feb 2026 | v6.20 |
  | 4727 | 4215 | May 2026 | v6.33 |
  | 4733 | 4221 | Jun 2026 | v6.44 |
  | 4738 | 4226 | Sep 2026 | v7.00 |
  | 4746 | 4234 | Nov 2026 (build 26463810) | v7.10 |

  The large key additions (v6.20 +22, v6.40 +37, v7.00 +46, v7.10 +29) are exactly the content updates that bumped the save version.

### Recommendation

- **The snapshot header records provenance.** The fields are:
  - `mbincompiler_tag`, `mbincompiler_sha256` and `tested_buildid` (from `report.json`)
  - `game_buildid` and `game_branch` (from the appmanifest)
  - `save_base_version` = the highest `Version % 512` among local saves at build time (138 today)
- **Runtime check.** `meta()` already reads the root `Version`, so the check costs nothing. If `save.Version % 512 > snapshot.save_base_version`, add one note (and a JSON field) saying the save is newer than the bundled catalog and mapping and the refresh command should be run. Unknown ids already print raw.
- **The refresh stays a manual dev command.** It needs the install, a .NET 8 runtime, a network fetch and a commit.

### Part 4: rejected alternatives

- **Trigger on every game update (BuildID change).** There were 21 Steam builds in two months, and most change nothing for us:
  - v7.10→v7.14 mapping: +0 keys.
  - Table MXML byte-identical from tested build 26271400 to installed 26463810.
  - It also only works where the game is installed.
  - Keep the BuildID as provenance, not as the trigger.
- **Manual command only.** Nothing tells anyone when to run it. That is how the 6.11 snapshot ended up 92 keys short on 4746 saves without being noticed.
- **Counting unmapped keys or unknown ids at runtime.** Counting keys needs the full tree walk that lazy lookup avoids (50–160 ms, PROTOTYPE.md). Unknown ids are already shown raw, and a count says nothing about why.

---

## Open risks

- **Patch-level drift without a save-version bump.** Patches do sometimes add keys:
  - v7.03.2 added `ObliterateLingeringCommunityPortalData`.
  - v7.04.1 added `AllowedSpacePoiTypes`.
  - v7.07 added three VR user settings (`VREyeAiming`, …).

  The local saves cannot show whether the save `Version` rose with them. No save was written between 7.03 and 7.07, and the 4738 saves did not need those keys. If such a patch adds items or read-path keys, the trigger stays silent until the next bump. Unknown ids still print raw, and so far no unmapped key has sat on a path the implant reads (PROTOTYPE.md).
- **The dev machine runs the experimental branch.** Snapshots built here may name items that are not on the public build yet (harmless). `save_base_version` may be ahead of public saves, so the check stays quiet for them (also harmless).
- **The prerelease flag is manual upstream.** A newest release that stays `prerelease: true` is normal, so the selection rule must not filter on the flag.
- **One upstream for everything.** The compiler, test data and mapping all come from one maintainer group (`monkeyman192`). Upstream stalling would freeze both snapshots, with no current alternative. The npm source is already 14 months stale.
- **Runtime dependency.** MBINCompiler.exe needs .NET 8. If upstream drops net8 assets (7.x already ships `-dotnet10` variants), the dev setup needs .NET 10.
- **The `Version % 512` shortcut stops working at base version 4608,** about 370 bumps away. Use the full libNOM formula if that ever matters.
- **The GUID gate needs output parsing.** MBINCompiler has no strict flag in release builds; `ERROR_ON_BROKEN` is compile-time only. The build tool has to scan stdout for `File not recognized`, a message string that could change upstream.

## New questions surfaced

1. **Legacy id aliases.** Should the catalog name 2018-era ids through `legacyitemtable.mbin` (`ID` → `ConvertID`), e.g. show `COM1` as "Ferrite Dust (legacy)"? Locally that is 16 distinct ids in 39 slot occurrences, and 83 of the table's 154 `ConvertID`s are already named. This is a display decision for the implant.
2. **Base parts in `--search` / `--have`.** With `nms_basepartproducts` added, about 1,950 building parts become searchable names. Should `inventory --search` match them? Should items carry a `type` such as `BasePart` so that output can filter them?
3. **Naming base objects in `bases`/atlas.** Base objects become 99.9% nameable. Should `bases` (or the atlas contract in #14) expose per-base object counts by name? That is a scope question for #14, not this ticket.
4. **The staleness note in `--json`.** Does the save-newer-than-snapshot note change the `nms.status/1` and `nms.inventory/1` schemas? Is it a new optional field (no bump) or `/2`? It ties to the schema versioning in #20 and the documentation in #6.
5. **One refresh command or two.** Should the catalog and the mapping be refreshed by one `tools/` script sharing a single MBINCompiler pin and provenance header? Recommended: yes. The open question is whether `mapping.json`'s legacy and savewizard layers are rebuilt from source files or only extended. PR #18's header names `mapping_legacy.json` and `mapping_savewizard.json`, but no branch on origin contains them (`git log --all` finds no such path). A refresh can therefore only extend the bundled merged file.

Out of scope: MBINCompiler's 6 known-broken templates (`GCSCENEOPTIONS.GLOBAL`, `DEFAULTSAVEDATA`, three `.ANIM` files, `LAUNCHTUBEDATA.ENTITY` per `report.json` `failed`). None of them is a table the catalog reads.
