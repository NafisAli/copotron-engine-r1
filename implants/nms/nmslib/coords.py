"""Galactic coordinates: one Address type and every notation NMS uses for it.

Extracted from nms-copilot `nms-core/src/{address,glyph,galaxy}.rs` and
`nms-save/src/address.rs`.

Bit layouts
-----------
48-bit portal / galactic address (glyph order, one nibble per glyph):
    P SSS YY ZZZ XXX   planet:4  system:12  y:8  z:12  x:12
56-bit packed save address (discovery `UA`, base `GalacticAddress`):
    P SSS GG YY ZZZ XXX   adds the galaxy (reality index) byte at bits 32..39
Voxel x/z are signed 12-bit, y signed 8-bit, all two's complement.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"

LY_PER_VOXEL = 400.0
# Mean distance between two random points in a unit cube (Robbins constant):
# the expected gap between two systems that share a region.
SAME_REGION_LY = 0.661707182 * LY_PER_VOXEL

SSI_BLACK_HOLE = 0x079
SSI_ATLAS_INTERFACE = 0x07A

# (name, emoji) indexed by glyph value; emoji per nms-core GLYPH_TABLE.
GLYPHS = [
    ("Sunset", "\U0001F305"), ("Bird", "\U0001F54A"), ("Face", "\U0001F611"),
    ("Diplo", "\U0001F995"), ("Eclipse", "\U0001F31C"), ("Balloon", "\U0001F388"),
    ("Boat", "⛵"), ("Bug", "\U0001F41C"), ("Dragonfly", "\U0001F98B"),
    ("Galaxy", "\U0001F300"), ("Voxel", "\U0001F54B"), ("Whale", "\U0001F40B"),
    ("Tent", "⛺"), ("Rocket", "\U0001F680"), ("Tree", "\U0001F333"),
    ("Atlas", "\U0001F53A"),
]


@lru_cache(maxsize=1)
def galaxies() -> list[dict]:
    return json.loads((DATA / "galaxies.json").read_text(encoding="utf-8"))["galaxies"]


def galaxy_name(index: int) -> str:
    return galaxies()[index]["name"]


def parse_galaxy(text: str | int) -> int:
    """Galaxy by index (0-255, or 1-based `#N` as the game numbers them) or by name."""
    if isinstance(text, int):
        return _check_range("galaxy", text, 0, 255)
    t = text.strip()
    if t.startswith("#") and t[1:].isdigit():
        return _check_range("galaxy", int(t[1:]) - 1, 0, 255)
    if t.isdigit():
        return _check_range("galaxy", int(t), 0, 255)
    for g in galaxies():
        if g["name"].lower() == t.lower():
            return g["index"]
    raise ValueError(f"unknown galaxy: {text}")


def _check_range(what: str, value: int, lo: int, hi: int) -> int:
    if not lo <= value <= hi:
        raise ValueError(f"{what} {value} is outside {lo}..{hi}")
    return value


def _signed(raw: int, bits: int) -> int:
    return raw - (1 << bits) if raw & (1 << (bits - 1)) else raw


@dataclass(frozen=True, slots=True)
class Address:
    """A point in the universe: galaxy, region (voxel), system and planet."""

    galaxy: int
    x: int  # voxel, -2048..2047
    y: int  # voxel, -128..127
    z: int  # voxel, -2048..2047
    system: int  # solar system index, 0..4095
    planet: int = 0  # 0..15

    def __post_init__(self) -> None:
        _check_range("galaxy", self.galaxy, 0, 255)
        _check_range("voxel x", self.x, -2048, 2047)
        _check_range("voxel y", self.y, -128, 127)
        _check_range("voxel z", self.z, -2048, 2047)
        _check_range("system index", self.system, 0, 4095)
        _check_range("planet index", self.planet, 0, 15)

    # ---- constructors -------------------------------------------------------
    @classmethod
    def from_packed48(cls, packed: int, galaxy: int = 0) -> Address:
        return cls(
            galaxy=galaxy,
            x=_signed(packed & 0xFFF, 12),
            z=_signed((packed >> 12) & 0xFFF, 12),
            y=_signed((packed >> 24) & 0xFF, 8),
            system=(packed >> 32) & 0xFFF,
            planet=(packed >> 44) & 0xF,
        )

    @classmethod
    def from_packed56(cls, value: int | str) -> Address:
        """Decode a save's packed address (int or hex string), galaxy included."""
        if isinstance(value, str):
            digits = value[2:] if value[:2].lower() == "0x" else value
            if not digits or len(digits) > 14:
                raise ValueError(f"invalid packed address: {value!r}")
            packed = int(digits, 16)
        elif isinstance(value, int) and not isinstance(value, bool):
            packed = value
        else:
            raise ValueError(f"invalid packed address: {value!r}")
        if not 0 <= packed <= 0x00FF_FFFF_FFFF_FFFF:
            raise ValueError(f"packed address exceeds 56 bits: {value!r}")
        return cls(
            galaxy=(packed >> 32) & 0xFF,
            x=_signed(packed & 0xFFF, 12),
            z=_signed((packed >> 12) & 0xFFF, 12),
            y=_signed((packed >> 24) & 0xFF, 8),
            system=(packed >> 40) & 0xFFF,
            planet=(packed >> 52) & 0xF,
        )

    @classmethod
    def from_universe_address(cls, ua: dict) -> Address:
        """Decode the expanded `UniverseAddress` object used for the player."""
        ga = ua.get("GalacticAddress") or {}
        return cls(
            galaxy=int(ua.get("RealityIndex", 0)),
            x=int(ga.get("VoxelX", 0)),
            y=int(ga.get("VoxelY", 0)),
            z=int(ga.get("VoxelZ", 0)),
            system=int(ga.get("SolarSystemIndex", 0)),
            planet=int(ga.get("PlanetIndex", 0)),
        )

    @classmethod
    def from_glyphs(cls, text: str, galaxy: int = 0) -> Address:
        return cls.from_packed48(int(parse_glyphs(text), 16), galaxy)

    @classmethod
    def from_signal_booster(cls, text: str, galaxy: int = 0, planet: int = 0) -> Address:
        parts = text.strip().split(":")
        if len(parts) != 4:
            raise ValueError(f"signal booster must be XXXX:YYYY:ZZZZ:SSSS, got {text!r}")
        try:
            sx, sy, sz, ssi = (int(p, 16) for p in parts)
        except ValueError:
            raise ValueError(f"invalid hex in signal booster {text!r}") from None
        packed = (
            (planet & 0xF) << 44
            | (ssi & 0xFFF) << 32
            | ((sy + 0x81) & 0xFF) << 24
            | ((sz + 0x801) & 0xFFF) << 12
            | ((sx + 0x801) & 0xFFF)
        )
        return cls.from_packed48(packed, galaxy)

    # ---- notations ----------------------------------------------------------
    @property
    def packed48(self) -> int:
        return (
            self.planet << 44
            | self.system << 32
            | (self.y & 0xFF) << 24
            | (self.z & 0xFFF) << 12
            | (self.x & 0xFFF)
        )

    @property
    def glyphs(self) -> str:
        """Portal address as 12 hex glyphs; identical digits to the 48-bit address."""
        return f"{self.packed48:012X}"

    @property
    def glyph_emoji(self) -> str:
        return "".join(GLYPHS[int(c, 16)][1] for c in self.glyphs)

    @property
    def galactic_address(self) -> str:
        return f"0x{self.packed48:012X}"

    @property
    def signal_booster(self) -> str:
        sx = ((self.x & 0xFFF) + 0x7FF) & 0xFFF
        sy = ((self.y & 0xFF) + 0x7F) & 0xFF
        sz = ((self.z & 0xFFF) + 0x7FF) & 0xFFF
        return f"{sx:04X}:{sy:04X}:{sz:04X}:{self.system:04X}"

    @property
    def voxel(self) -> tuple[int, int, int]:
        return (self.x, self.y, self.z)

    @property
    def galaxy_name(self) -> str:
        return galaxy_name(self.galaxy)

    @property
    def system_key(self) -> tuple[int, int, int, int, int]:
        """Identity of the star system (planet dropped)."""
        return (self.galaxy, self.x, self.y, self.z, self.system)

    @property
    def is_black_hole(self) -> bool:
        return self.system == SSI_BLACK_HOLE

    @property
    def is_atlas_interface(self) -> bool:
        return self.system == SSI_ATLAS_INTERFACE

    def same_region(self, other: Address) -> bool:
        return self.galaxy == other.galaxy and self.voxel == other.voxel

    def same_system(self, other: Address) -> bool:
        return self.same_region(other) and self.system == other.system

    def distance_ly(self, other: Address) -> float | None:
        """Light-years between systems; None across galaxies (no meaningful distance)."""
        if self.galaxy != other.galaxy:
            return None
        if self.same_system(other):
            return 0.0
        if self.same_region(other):
            return SAME_REGION_LY
        return math.dist(self.voxel, other.voxel) * LY_PER_VOXEL

    @property
    def distance_to_core_ly(self) -> float:
        return math.dist(self.voxel, (0, 0, 0)) * LY_PER_VOXEL

    def to_json(self) -> dict:
        return {
            "galaxy": self.galaxy,
            "galaxy_name": self.galaxy_name,
            "glyphs": self.glyphs,
            "glyph_emoji": self.glyph_emoji,
            "signal_booster": self.signal_booster,
            "galactic_address": self.galactic_address,
            "voxel": {"x": self.x, "y": self.y, "z": self.z},
            "system_index": self.system,
            "planet_index": self.planet,
        }


def parse_glyphs(text: str) -> str:
    """Parse 12 glyphs given as hex digits, emoji or glyph names; return 12 hex chars.

    Separators (space, colon, dash) are allowed. Mirrors nms-core `parse_next_glyph`:
    longest emoji first, then names, then single hex digits.
    """
    rest = text.strip()
    if rest[:2].lower() == "0x":
        rest = rest[2:]
    # Pure hex first: otherwise "0FACE..." would read the glyph name "Face".
    compact = "".join(c for c in rest if c not in " :-_,")
    if len(compact) == 12 and all(c in "0123456789abcdefABCDEF" for c in compact):
        return compact.upper()
    by_emoji = sorted(enumerate(GLYPHS), key=lambda e: -len(e[1][1]))
    by_name = sorted(enumerate(GLYPHS), key=lambda e: -len(e[1][0]))
    out: list[int] = []
    while rest:
        if rest[0] in " :-_,":
            rest = rest[1:]
            continue
        for i, (_, emoji) in by_emoji:
            if rest.startswith(emoji):
                out.append(i)
                rest = rest[len(emoji):].removeprefix("️")
                break
        else:
            for i, (name, _) in by_name:
                if rest.lower().startswith(name.lower()):
                    out.append(i)
                    rest = rest[len(name):]
                    break
            else:
                c = rest[0]
                if c in "0123456789abcdefABCDEF":
                    out.append(int(c, 16))
                    rest = rest[1:]
                else:
                    raise ValueError(f"unrecognised glyph at: {rest[:12]!r}")
    if len(out) != 12:
        raise ValueError(f"expected 12 glyphs, got {len(out)}")
    return "".join(f"{g:X}" for g in out)
