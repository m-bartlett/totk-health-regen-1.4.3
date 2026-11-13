"""Helpers for decompressing/recompressing TotK .zs files using the game's
zstd dictionaries (extracted from romfs/Pack/ZsDic.pack.zs), and for
reading/writing SARC archives via oead.

Usage as a library:
    from totk_zs import ZsHelper
    zs = ZsHelper("/path/to/.../romfs")
    data = zs.decompress_file("Pack/Actor/Player.pack.zs")
    sarc = oead.Sarc(data)
"""
from __future__ import annotations

import pathlib
import oead
import zstandard


class ZsHelper:
    def __init__(self, romfs_root: str | pathlib.Path):
        self.romfs_root = pathlib.Path(romfs_root)
        zsdic_path = self.romfs_root / "Pack" / "ZsDic.pack.zs"
        raw = zstandard.ZstdDecompressor().decompress(
            zsdic_path.read_bytes(), max_output_size=200 * 1024 * 1024
        )
        sarc = oead.Sarc(raw)

        def dict_bytes(name):
            f = sarc.get_file(name)
            return bytes(f.data) if f else None

        self.dict_default = dict_bytes("zs.zsdic")
        self.dict_bcett = dict_bytes("bcett.byml.zsdic")
        self.dict_pack = dict_bytes("pack.zsdic")

        self._decompressors = []
        for d in (self.dict_pack, self.dict_bcett, self.dict_default):
            if d:
                self._decompressors.append(
                    zstandard.ZstdDecompressor(dict_data=zstandard.ZstdCompressionDict(d))
                )
        self._decompressors.append(zstandard.ZstdDecompressor())

    def decompress(self, data: bytes) -> bytes:
        # TotK uses different zstd dictionaries depending on file kind
        # (pack.zsdic for .pack.zs/.byml.zs/.rsizetable.zs, bcett.byml.zsdic
        # for terrain bake files, zs.zsdic for everything else, and some
        # files like ZsDic.pack.zs itself use no dictionary at all).
        last_err = None
        for dctx in self._decompressors:
            try:
                return dctx.decompress(data, max_output_size=256 * 1024 * 1024)
            except zstandard.ZstdError as e:
                last_err = e
        raise last_err

    def decompress_file(self, rel_path: str) -> bytes:
        path = self.romfs_root / rel_path
        return self.decompress(path.read_bytes())

    def compress(self, data: bytes, level: int = 19) -> bytes:
        cctx = zstandard.ZstdCompressor(
            level=level,
            dict_data=zstandard.ZstdCompressionDict(self.dict_pack) if self.dict_pack else None,
        )
        return cctx.compress(data)
