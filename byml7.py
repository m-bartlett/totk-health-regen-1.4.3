"""Minimal, read-only parser for TotK's BYML v7 "hash-keyed" container
format (used by .bgyml files like BSAParam, and by GameDataList).

This isn't a general-purpose BYML library - oead (the pip-installable one)
only documents support for versions 1-4, and TotK's BSAParam/GameDataList
files are version 7, which adds 0x20/0x21 hash-by-numeric-key container
nodes on top of the v2-4 format described at
https://zeldamods.org/wiki/BYML. This module implements just enough of
that spec (string tables, 0x20 hash nodes, and the value node types we
actually see: bool/int/uint/float/string) to inspect whether a given field
is populated in a stock game file, for diagnostic purposes.
"""
from __future__ import annotations

import struct
import zlib


def _crc32_hash(name: str) -> int:
    return zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF


class Byml7:
    def __init__(self, data: bytes):
        self.data = data
        magic = data[0:2]
        if magic == b"BY":
            self.endian = ">"
        elif magic == b"YB":
            self.endian = "<"
        else:
            raise ValueError(f"not a BYML file (magic={magic!r})")
        self.version = struct.unpack_from(self.endian + "H", data, 2)[0]
        self.hash_key_table_offset = struct.unpack_from(self.endian + "I", data, 4)[0]
        self.string_table_offset = struct.unpack_from(self.endian + "I", data, 8)[0]
        self.root_node_offset = struct.unpack_from(self.endian + "I", data, 12)[0]
        self._hash_key_strings = (
            self._read_string_table(self.hash_key_table_offset)
            if self.hash_key_table_offset
            else []
        )
        self._strings = (
            self._read_string_table(self.string_table_offset)
            if self.string_table_offset
            else []
        )

    def _u32(self, off):
        return struct.unpack_from(self.endian + "I", self.data, off)[0]

    def _type_and_count(self, off):
        node_type = self.data[off]
        byteorder = "little" if self.endian == "<" else "big"
        count = int.from_bytes(self.data[off + 1 : off + 4], byteorder)
        return node_type, count

    def _read_string_table(self, off):
        node_type, count = self._type_and_count(off)
        assert node_type == 0xC2, f"expected string table (0xC2) at {off:#x}, got {node_type:#x}"
        offsets = [self._u32(off + 4 + 4 * i) for i in range(count + 1)]
        strings = []
        for i in range(count):
            start = off + offsets[i]
            end = off + offsets[i + 1]
            strings.append(self.data[start:end].rstrip(b"\x00").decode("utf-8"))
        return strings

    def _read_value(self, node_type: int, raw: bytes):
        if node_type == 0xA0:  # string (index into string table)
            (idx,) = struct.unpack(self.endian + "I", raw)
            return self._strings[idx]
        if node_type == 0xD0:  # bool
            (v,) = struct.unpack(self.endian + "I", raw)
            return bool(v)
        if node_type == 0xD1:  # int32
            (v,) = struct.unpack(self.endian + "i", raw)
            return v
        if node_type == 0xD2:  # float
            (v,) = struct.unpack(self.endian + "f", raw)
            return v
        if node_type == 0xD3:  # uint32
            (v,) = struct.unpack(self.endian + "I", raw)
            return v
        if node_type == 0xFF:  # null
            return None
        if node_type in (0x20, 0x21, 0xC0, 0xC1):
            (off,) = struct.unpack(self.endian + "I", raw)
            return self._read_container(node_type, off)
        raise NotImplementedError(f"unsupported node type {node_type:#x}")

    def _read_container(self, node_type: int, off: int):
        if node_type == 0x20:
            return self._read_hash_node(off)
        if node_type == 0xC0:
            return self._read_array_node(off)
        if node_type == 0xC1:
            return self._read_string_hash_node(off)
        raise NotImplementedError(f"container type {node_type:#x} not implemented")

    def _read_string_hash_node(self, off):
        """0xC1 - hash keyed by a string (an index into the hash key table)."""
        node_type, count = self._type_and_count(off)
        assert node_type == 0xC1
        entries_off = off + 4
        byteorder = "little" if self.endian == "<" else "big"
        result = {}
        for i in range(count):
            entry_off = entries_off + 8 * i
            name_idx = int.from_bytes(self.data[entry_off : entry_off + 3], byteorder)
            entry_type = self.data[entry_off + 3]
            raw = self.data[entry_off + 4 : entry_off + 8]
            name = self._hash_key_strings[name_idx]
            result[name] = self._read_value(entry_type, raw)
        return result

    def _read_hash_node(self, off):
        """0x20 - hash of 32-bit numeric key -> value."""
        node_type, count = self._type_and_count(off)
        assert node_type == 0x20
        entries_off = off + 4
        types_off = entries_off + 8 * count
        result = {}
        for i in range(count):
            key_hash = self._u32(entries_off + 8 * i)
            raw = self.data[entries_off + 8 * i + 4 : entries_off + 8 * i + 8]
            entry_type = self.data[types_off + i]
            result[key_hash] = self._read_value(entry_type, raw)
        return result

    def _read_array_node(self, off):
        node_type, count = self._type_and_count(off)
        assert node_type == 0xC0
        types = self.data[off + 4 : off + 4 + count]
        values_off = off + 4 + ((count + 3) // 4) * 4
        result = []
        for i in range(count):
            entry_type = types[i]
            raw = self.data[values_off + 4 * i : values_off + 4 * i + 4]
            result.append(self._read_value(entry_type, raw))
        return result

    def root(self):
        node_type, _ = self._type_and_count(self.root_node_offset)
        return self._read_container(node_type, self.root_node_offset)

    def field(self, name: str):
        """Look up a field on the root node (a string hash, 0xC1) by name."""
        return self.root().get(name)

    def has_field(self, name: str) -> bool:
        return name in self.root()


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    field = sys.argv[2] if len(sys.argv) > 2 else None
    b = Byml7(open(path, "rb").read())
    print(f"version={b.version} endian={'big' if b.endian == '>' else 'little'}")
    root = b.root()
    print(f"{len(root)} populated root fields")
    if field:
        print(field, "->", b.field(field))
    else:
        for k, v in root.items():
            print(f"  {k!r} -> {v!r}")