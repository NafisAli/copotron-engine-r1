import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

UID = "76561190000000001"


def player_state(**overrides) -> dict:
    ps = {
        "UniverseAddress": {"RealityIndex": 9, "GalacticAddress": {
            "VoxelX": 1701, "VoxelY": -2, "VoxelZ": -578, "SolarSystemIndex": 95, "PlanetIndex": 0}},
        "PreviousUniverseAddress": {"RealityIndex": 0, "GalacticAddress": {
            "VoxelX": 0, "VoxelY": 0, "VoxelZ": 0, "SolarSystemIndex": 0, "PlanetIndex": 0}},
        "Units": -1,  # stored signed; the game reads it as u32
        "Nanites": 48,
        "Specials": 7,
        "SaveSummary": "Aboard Test Station",
        "DifficultyState": {"Preset": {"DifficultyPresetType": "Survival"}},
        "PrimaryShip": 1,
        "ActiveMultioolIndex": 0,
        "Inventory": {"ValidSlotIndices": [{}] * 26, "Width": 10, "Height": 12, "Slots": [
            slot("^YELLOW2", 500, 500), slot("^YELLOW2", 143, 500), slot("^FUEL1", 460, 500),
            slot("^NOT_A_REAL_ITEM", 3, 10), slot("^MAINT_TECH3", 50, 50)]},
        "Inventory_Cargo": {"ValidSlotIndices": [], "Slots": []},
        "Inventory_TechOnly": {"ValidSlotIndices": [{}] * 11, "Slots": [
            slot("^JET1", 1, 1, "Technology")]},
        "ShipOwnership": [
            ship("", "MODELS/COMMON/SPACECRAFT/SHUTTLE/SHUTTLE_PROC.SCENE.MBIN", [slot("^YELLOW2", 7, 1000)]),
            ship("Boundary Herald", "MODELS/COMMON/SPACECRAFT/FIGHTERS/FIGHTER_PROC.SCENE.MBIN",
                 [slot("^ASTEROID2", 141, 1000)]),
            ship("", "", []),  # empty ownership slot
        ],
        "Multitools": [{"Name": "", "Resource": {"Filename": "MODELS/.../MULTITOOL.SCENE.MBIN"},
                        "Store": {"ValidSlotIndices": [{}] * 8, "Slots": [slot("^LASER", 1, 1, "Technology")]}}],
        "Chest4Inventory": {"ValidSlotIndices": [{}] * 50, "Slots": [slot("^YELLOW2", 9, 500)]},
        "Chest5Inventory": {"ValidSlotIndices": [{}] * 50, "Slots": []},
        "VehicleOwnership": [
            {"Name": "", "Inventory": {"ValidSlotIndices": [{}] * 40, "Slots": []},
             "Inventory_TechOnly": {"ValidSlotIndices": [{}] * 28, "Slots": [slot("^VEHICLE_ENGINE", 1, 1, "Technology")]}},
            {}, {}, {}, {},
            {"Name": "", "Inventory": {"ValidSlotIndices": [{}] * 40, "Slots": [slot("^FUEL1", 5, 250)]},
             "Inventory_TechOnly": {"ValidSlotIndices": [{}] * 28, "Slots": []}},
        ],
        "PersistentPlayerBases": [
            base("Home", "HomePlanetBase", 4544285833422501, UID),  # 0x10250000FEDBE6A5-style packed int
            base("Visited", "ExternalPlanetBase", "0x40050003AB8C07", "999"),
        ],
    }
    ps.update(overrides)
    return ps


def slot(item_id, amount, max_amount, kind="Substance"):
    return {"Type": {"InventoryType": kind}, "Id": item_id, "Amount": amount, "MaxAmount": max_amount,
            "DamageFactor": 0.0, "FullyInstalled": True, "Index": {"X": 0, "Y": 0}}


def ship(name, filename, slots):
    return {"Name": name, "Resource": {"Filename": filename},
            "Inventory": {"ValidSlotIndices": [{}] * 25, "Class": {"InventoryClass": "B"}, "Slots": slots},
            "Inventory_Cargo": {"ValidSlotIndices": [], "Slots": []},
            "Inventory_TechOnly": {"ValidSlotIndices": [{}] * 13, "Slots": []}}


def base(name, kind, address, uid):
    return {"Name": name, "BaseType": {"PersistentBaseTypes": kind}, "GalacticAddress": address,
            "Position": [1.0, 2.0, 3.0], "Owner": {"UID": uid, "USN": "someone", "LID": ""},
            "LastUpdateTimestamp": 1793449091, "Objects": [{}, {}]}


def record(dt, ua, vp=None, name=None, uid=UID, usn="TrafficPolice"):
    r = {"DD": {"UA": ua, "DT": dt, "VP": vp or ["0x1"]}, "DM": {},
         "OWS": {"LID": uid if uid == UID else "", "UID": uid, "USN": usn, "TS": 1793451316}}
    if name:
        r["DM"]["CN"] = name
    return r


def save_doc(context="Main", **ps_overrides) -> dict:
    ps = player_state(**ps_overrides)
    doc = {
        "Version": 4746, "Platform": "Win|Final", "ActiveContext": context,
        "CommonStateData": {"SaveName": "Test", "TotalPlayTime": 8391},
        "DiscoveryManagerData": {"DiscoveryData-v1": {"Store": {"Record": [
            # galaxy 9 system matching the player location (planet bits 52.., galaxy bits 32..)
            record("SolarSystem", "0x005F09FEDBE6A5", name="Testoria"),
            record("Planet", "0x205F09FEDBE6A5", vp=["0xADA4F8054BD46AB5", 2]),
            record("Planet", "0x305F09FEDBE6A5", vp=["0x1", (1 << 16) | 3], name="Glowball"),
            record("Animal", 4544285833422501, uid="42", usn="other"),
        ]}}},
    }
    ctx = {"GameMode": 1, "PlayerStateData": ps}
    doc["ExpeditionContext" if context in ("Expedition", "Season") else "BaseContext"] = ctx
    return doc


@pytest.fixture
def nms_root(tmp_path, monkeypatch):
    """A fake HelloGames/NMS root with one Steam account; plaintext saves need no lz4."""
    acct = tmp_path / "NMS" / f"st_{UID}"
    acct.mkdir(parents=True)
    monkeypatch.setenv("NMS_SAVE_PATH", str(tmp_path / "NMS"))
    return acct


def write_save(path: Path, doc: dict, mtime: float) -> Path:
    import os
    path.write_text(json.dumps(doc), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path
