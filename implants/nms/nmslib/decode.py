"""Read-only decoding of a `.hg` save into a JSON tree read by readable key names.

Extracted from nms-copilot `nms-save/src/{decompress,mapping,lib}.rs`.
Never writes to the save: files are opened "rb" and nothing else.

Key lookup is lazy. An obfuscated save is not walked and renamed (that costs
50-160 ms on real saves). Instead `decode_bytes` returns a read-only `Node` view
that maps each readable name to its on-disk key when it is looked up, so only
the paths the extractor reads are touched. A plaintext save is returned as is.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

try:  # about 2x faster than the stdlib on 2-9 MB saves
    import orjson

    def _loads(data: bytes):
        return orjson.loads(data)
except ImportError:  # the engine's test env runs without it
    def _loads(data: bytes):
        return json.loads(data)

BLOCK_MAGIC = 0xFEEDA1E5
BLOCK_HEADER = struct.Struct("<IIII")  # magic, compressed, decompressed, reserved
MAX_CHUNK = 0x80000
MAPPING_PATH = Path(__file__).parent / "data" / "mapping.json"


class SaveDecodeError(Exception):
    pass


def decompress(raw: bytes) -> bytes:
    """Plaintext JSON passes through; otherwise concatenate the LZ4 raw blocks."""
    if raw[:1] == b"{":
        return raw
    import lz4.block  # deferred so plaintext saves and tests need no native dependency

    out = bytearray()
    offset = 0
    while offset < len(raw):
        if offset + BLOCK_HEADER.size > len(raw):
            raise SaveDecodeError(f"truncated block header at offset {offset}")
        magic, csize, dsize, _ = BLOCK_HEADER.unpack_from(raw, offset)
        if magic != BLOCK_MAGIC:
            raise SaveDecodeError(f"bad block magic 0x{magic:08X} at offset {offset}")
        if dsize > MAX_CHUNK:
            raise SaveDecodeError(f"block at offset {offset} declares {dsize} bytes (> 0x80000)")
        offset += BLOCK_HEADER.size
        if offset + csize > len(raw):
            raise SaveDecodeError(f"truncated block payload at offset {offset}")
        try:
            out += lz4.block.decompress(raw[offset:offset + csize], uncompressed_size=dsize)
        except Exception as e:  # lz4 raises a bare LZ4BlockError
            raise SaveDecodeError(f"LZ4 block at offset {offset - BLOCK_HEADER.size}: {e}") from None
        offset += csize
    return bytes(out)


@lru_cache(maxsize=1)
def _mapping() -> tuple[dict[str, str], dict[str, str]]:
    """(obfuscated -> readable keys, readable renames applied after lookup)."""
    m = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return m["keys"], m["fixups"]


@lru_cache(maxsize=1)
def _names() -> tuple[dict[str, str], dict[str, str]]:
    """(readable -> on-disk key, on-disk key -> readable), fixups applied."""
    keys, fixups = _mapping()
    readable = {o: fixups.get(r, r) for o, r in keys.items()}
    return {r: o for o, r in readable.items()}, readable


def _view(value):
    if isinstance(value, dict):
        return Node(value)
    if isinstance(value, list):
        return NodeList(value)
    return value


class Node(Mapping):
    """Read-only view of an obfuscated object, indexed by readable key names."""

    __slots__ = ("_raw",)

    def __init__(self, raw: dict):
        self._raw = raw

    def __getitem__(self, name: str):
        on_disk = _names()[0].get(name, name)
        return _view(self._raw[on_disk])

    def get(self, name: str, default=None):
        on_disk = _names()[0].get(name, name)
        return _view(self._raw[on_disk]) if on_disk in self._raw else default

    def __contains__(self, name) -> bool:
        return _names()[0].get(name, name) in self._raw

    def __iter__(self):
        readable = _names()[1]
        return (readable.get(k, k) for k in self._raw)

    def __len__(self) -> int:
        return len(self._raw)


class NodeList(Sequence):
    """Read-only view of a list inside an obfuscated save; items are viewed on access."""

    __slots__ = ("_raw",)

    def __init__(self, raw: list):
        self._raw = raw

    def __getitem__(self, i):
        if isinstance(i, slice):
            return NodeList(self._raw[i])
        return _view(self._raw[i])

    def __len__(self) -> int:
        return len(self._raw)


def is_obfuscated(doc) -> bool:
    if not isinstance(doc, dict):
        return False
    if "F2P" in doc:
        return True
    if "Version" in doc:
        return False
    return "6f=" in doc or "8>q" in doc


def parse(raw: bytes):
    """Decompressed bytes -> raw JSON value. Bad UTF-8 becomes U+FFFD, never a crash."""
    data = decompress(raw).rstrip(b"\0")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        data = data.decode("utf-8", errors="replace").encode("utf-8")
    try:
        return _loads(data)
    except ValueError as e:  # json.JSONDecodeError and orjson.JSONDecodeError
        raise SaveDecodeError(f"save JSON does not parse: {e}") from None


def view(doc) -> Mapping:
    """Raw save root -> a mapping read by readable key names."""
    if not isinstance(doc, dict):
        raise SaveDecodeError("save JSON root is not an object")
    return Node(doc) if is_obfuscated(doc) else doc


def decode_bytes(raw: bytes) -> Mapping:
    return view(parse(raw))


def read_save(path: Path) -> Mapping:
    with open(path, "rb") as f:  # read-only, always
        return decode_bytes(f.read())
