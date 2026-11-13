"""Minimal, narrowly-scoped BYML v7 writer: sets one existing string-typed
root field to a new string value, growing the value string table as
needed. This is NOT a general BYML writer - see byml7.py's docstring for
why (oead only supports BYML versions 1-4; TotK's .bgyml files are v7).

Only handles the one shape of edit this project needs: changing the value
of a root-level string field that already exists (as an empty string) in
a 0xC1 (string-hash) root node. It does this by:

  1. Appending the new string to the end of the existing value string
     table (growing its offset-index array by one entry too).
  2. Walking the ENTIRE file recursively to find every absolute
     byte-offset reference to a nested container (hash/array nodes always
     store these as raw 4-byte file offsets), and shifting any of them
     that point at or past the old string-table end forward by however
     many bytes we inserted (since everything after the string table -
     the root node and all its nested data - moves later in the file).
  3. Updating the one value-table entry whose key matches to point at
     the new string's index.
  4. Updating the file header's root_node_offset by the same shift.

Self-verifies by re-parsing the patched bytes with byml7.Byml7 and
confirming the target field now reads back correctly, and that every
other field is unchanged.
"""
from __future__ import annotations

import struct
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import byml7  # noqa: E402


def _align4(n: int) -> int:
    return (n + 3) & ~3


def set_string_field(data: bytes, field_name: str, new_value: str) -> bytes:
    p = byml7.Byml7(data)
    assert p.has_field(field_name), f"{field_name!r} not present in root"
    old_value = p.field(field_name)
    assert isinstance(old_value, str), f"{field_name!r} is not a string field (got {old_value!r})"

    endian = p.endian
    data = bytearray(data)

    # --- locate the root node's entry for this field, to patch its value index later ---
    hash_key_idx = p._hash_key_strings.index(field_name)
    root_off = p.root_node_offset
    root_type, root_count = p._type_and_count(root_off)
    assert root_type == 0xC1, f"root node is type {root_type:#x}, expected 0xC1 (string hash)"
    entries_off = root_off + 4
    target_entry_off = None
    for i in range(root_count):
        entry_off = entries_off + 8 * i
        byteorder = "little" if endian == "<" else "big"
        name_idx = int.from_bytes(data[entry_off: entry_off + 3], byteorder)
        entry_type = data[entry_off + 3]
        if name_idx == hash_key_idx:
            assert entry_type == 0xA0, f"field {field_name!r} is not a string entry (type {entry_type:#x})"
            target_entry_off = entry_off
            break
    assert target_entry_off is not None, "could not re-locate field entry"

    # --- grow the string (value) table ---
    st_off = p.string_table_offset
    st_type, st_count = p._type_and_count(st_off)
    assert st_type == 0xC2
    old_offsets = [p._u32(st_off + 4 + 4 * i) for i in range(st_count + 1)]
    old_table_total_len = old_offsets[-1]  # relative to st_off
    old_table_end_abs = st_off + old_table_total_len

    new_string_bytes = new_value.encode("utf-8") + b"\x00"
    new_offset_slot_bytes = 4  # one more 4-byte offset entry in the offsets array
    # Everything in the table shifts: existing string data moves later by
    # new_offset_slot_bytes (since the offsets array itself grew), and the
    # new string is appended right after the (shifted) old string data.
    new_offsets = [o + new_offset_slot_bytes for o in old_offsets]
    new_offsets.append(new_offsets[-1] + len(new_string_bytes))
    new_string_index = st_count  # 0-based index of the newly appended string

    insertion_size = new_offset_slot_bytes + len(new_string_bytes)
    new_total_len = new_offsets[-1]

    # Build the new string-table bytes: header (type+count) + the grown
    # offsets array + each original string's exact original bytes
    # (re-sliced out via the OLD offsets) + the new string appended last.
    byteorder = "little" if endian == "<" else "big"
    new_table = bytearray()
    new_table += bytes([0xC2]) + (st_count + 1).to_bytes(3, byteorder)
    for o in new_offsets:
        new_table += struct.pack(endian + "I", o)
    for i in range(st_count):
        raw_start = st_off + old_offsets[i]
        raw_end = st_off + old_offsets[i + 1]
        new_table += bytes(data[raw_start:raw_end])
    new_table += new_string_bytes
    assert len(new_table) == new_total_len, (len(new_table), new_total_len)

    # --- find every absolute container-reference offset in the file that
    # points at/after the old table end, to shift it forward ---
    shift_positions = []  # byte offsets (in the file) of 4-byte fields to shift

    def walk_hash(off):
        node_type, count = p._type_and_count(off)
        entries_off = off + 4
        if node_type == 0x20:
            types_off = entries_off + 8 * count
            for i in range(count):
                val_off = entries_off + 8 * i + 4
                entry_type = data[types_off + i]
                maybe_walk(entry_type, val_off)
        elif node_type == 0xC1:
            for i in range(count):
                val_off = entries_off + 8 * i + 4
                entry_type = data[entries_off + 8 * i + 3]
                maybe_walk(entry_type, val_off)
        elif node_type == 0xC0:
            types = data[off + 4: off + 4 + count]
            values_off = off + 4 + ((count + 3) // 4) * 4
            for i in range(count):
                val_off = values_off + 4 * i
                maybe_walk(types[i], val_off)
        else:
            raise NotImplementedError(node_type)

    visited = set()

    def maybe_walk(entry_type, val_off):
        if entry_type in (0x20, 0xC0, 0xC1):
            target = p._u32(val_off)
            if target >= old_table_end_abs:
                shift_positions.append(val_off)
            if val_off not in visited:
                visited.add(val_off)
                walk_hash(target)

    walk_hash(root_off)

    # --- apply the patch ---
    before = data[:st_off]
    after = data[old_table_end_abs:]
    patched = bytearray(before) + new_table + bytearray(after)

    # Fix up header root_node_offset.
    struct.pack_into(endian + "I", patched, 12, p.root_node_offset + insertion_size)

    # Fix up every discovered absolute offset (shift by insertion_size);
    # their byte *positions* also shifted if they live after old_table_end_abs.
    for pos in shift_positions:
        new_pos = pos + insertion_size if pos >= old_table_end_abs else pos
        old_val = struct.unpack_from(endian + "I", patched, new_pos)[0]
        struct.pack_into(endian + "I", patched, new_pos, old_val + insertion_size)

    # Fix up the target field's value index (its own position also shifted).
    target_entry_off_new = target_entry_off + insertion_size if target_entry_off >= old_table_end_abs else target_entry_off
    struct.pack_into(endian + "I", patched, target_entry_off_new + 4, new_string_index)

    patched_bytes = bytes(patched)

    # Self-verify.
    check = byml7.Byml7(patched_bytes)
    got = check.field(field_name)
    assert got == new_value, f"verification failed: field reads back as {got!r}, expected {new_value!r}"
    orig_fields = p.root()
    new_fields = check.root()
    for k in orig_fields:
        if k == field_name:
            continue
        assert new_fields.get(k) == orig_fields[k], f"field {k!r} changed unexpectedly: {orig_fields[k]!r} -> {new_fields.get(k)!r}"
    assert set(new_fields) == set(orig_fields), "field set changed unexpectedly"

    return patched_bytes


if __name__ == "__main__":
    path = sys.argv[1]
    field = sys.argv[2]
    value = sys.argv[3]
    data = open(path, "rb").read()
    out = set_string_field(data, field, value)
    print(f"OK, {len(data)} -> {len(out)} bytes")
