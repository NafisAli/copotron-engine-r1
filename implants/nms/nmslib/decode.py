"""Read-only decoding of a `.hg` save into a deobfuscated JSON dict.

Extracted from nms-copilot `nms-save/src/{decompress,mapping,lib}.rs`.
Never writes to the save: files are opened "rb" and nothing else.
"""

from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path

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
    m = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return m["keys"], m["fixups"]


def _deobfuscate(value):
    keys, fixups = _mapping()

    def walk(v):
        if isinstance(v, dict):
            out = {}
            for k, child in v.items():
                name = keys.get(k, k)
                out[fixups.get(name, name)] = walk(child)
            return out
        if isinstance(v, list):
            return [walk(c) for c in v]
        return v

    return walk(value)


def is_obfuscated(doc) -> bool:
    if not isinstance(doc, dict):
        return False
    if "F2P" in doc:
        return True
    if "Version" in doc:
        return False
    return "6f=" in doc or "8>q" in doc


def decode_bytes(raw: bytes) -> dict:
    text = decompress(raw).rstrip(b"\0").decode("utf-8", errors="replace")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise SaveDecodeError(f"save JSON does not parse: {e}") from None
    if not isinstance(doc, dict):
        raise SaveDecodeError("save JSON root is not an object")
    return _deobfuscate(doc) if is_obfuscated(doc) else doc


def read_save(path: Path) -> dict:
    with open(path, "rb") as f:  # read-only, always
        return decode_bytes(f.read())
