"""Erzeugt installer/BewerbungDB.ico (blaues, abgerundetes Quadrat mit weißem B) ohne Fremdbibliotheken."""

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "installer" / "BewerbungDB.ico"
BLUE = (0x3B, 0x5B, 0xDB)
B_GLYPH = ["1111 ", "1   1", "1   1", "1111 ", "1   1", "1   1", "1111 "]  # 5x7


def render(size: int) -> bytes:
    radius = size * 0.22
    gw, gh = 5, 7
    cell = size * 0.62 / gh
    ox, oy = (size - cell * gw) / 2, (size - cell * gh) / 2
    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG-Filter: keiner
        for x in range(size):
            # abgerundetes Quadrat (mit 1px Kantenglättung)
            dx = max(radius - x - 0.5, x + 0.5 - (size - radius), 0)
            dy = max(radius - y - 0.5, y + 0.5 - (size - radius), 0)
            d = (dx * dx + dy * dy) ** 0.5
            alpha = 255 if d <= radius - 1 else max(0, int(255 * (radius - d))) if d < radius else 0
            gx, gy = int((x - ox) // cell), int((y - oy) // cell)
            white = 0 <= gx < gw and 0 <= gy < gh and B_GLYPH[gy][gx] == "1"
            r, g, b = (255, 255, 255) if white else BLUE
            row += bytes((r, g, b, alpha))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    sizes = [16, 32, 48, 256]
    pngs = [render(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, png in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(header + entries + b"".join(pngs))
    print("Icon erzeugt:", OUT)


if __name__ == "__main__":
    main()
