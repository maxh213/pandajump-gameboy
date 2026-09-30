"""The cartridge header of build/pandajump.gb (PROMPT.md, docs/DESIGN.md
"Toolchain": MBC5 + RAM + battery, one 8 KiB RAM bank, DMG only, title
PANDAJUMP)."""

NINTENDO_LOGO = bytes.fromhex(
    "CEED6666CC0D000B03730083000C000D0008111F8889000EDCCC6EE6DDDDD999"
    "BBBB67636E0EECCCDDDC999FBBB9333E"
)


def test_size_matches_header(rom_bytes):
    assert len(rom_bytes) >= 32 * 1024
    assert len(rom_bytes) == (32 * 1024) << rom_bytes[0x148], "file size disagrees with the ROM size code"


def test_title_is_pandajump(rom_bytes):
    title = rom_bytes[0x134:0x143]
    assert title.rstrip(b"\x00") == b"PANDAJUMP"
    assert set(title[len(b"PANDAJUMP"):]) <= {0}


def test_dmg_only(rom_bytes):
    assert rom_bytes[0x143] not in (0x80, 0xC0), "CGB flag set on a DMG-only game"


def test_cartridge_type_mbc5_ram_battery(rom_bytes):
    assert rom_bytes[0x147] == 0x1B


def test_ram_size_one_8k_bank(rom_bytes):
    assert rom_bytes[0x149] == 0x02


def test_nintendo_logo(rom_bytes):
    # A real DMG's boot ROM refuses to start without it.
    assert rom_bytes[0x104:0x134] == NINTENDO_LOGO


def test_header_checksum(rom_bytes):
    x = 0
    for b in rom_bytes[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    assert rom_bytes[0x14D] == x


def test_global_checksum(rom_bytes):
    total = (sum(rom_bytes) - rom_bytes[0x14E] - rom_bytes[0x14F]) & 0xFFFF
    assert (rom_bytes[0x14E] << 8 | rom_bytes[0x14F]) == total
