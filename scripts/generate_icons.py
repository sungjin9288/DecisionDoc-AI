"""Generate PWA icons from SVG using cairosvg or pillow fallback."""
import os
import struct
import zlib


def generate_icons():
    icon_dir = "app/static/icons"
    os.makedirs(icon_dir, exist_ok=True)

    # Try cairosvg first
    try:
        import cairosvg
        for size in [192, 512]:
            cairosvg.svg2png(
                url=f"{icon_dir}/icon.svg",
                write_to=f"{icon_dir}/icon-{size}.png",
                output_width=size,
                output_height=size,
            )
        print("Icons generated via cairosvg")
        return
    except ImportError:
        pass

    # Fallback: create minimal PNG programmatically
    def create_simple_png(size: int, path: str):
        """Create a simple purple square PNG (RGBA)."""
        img_data = []
        for y in range(size):
            row = [0]  # filter byte
            for x in range(size):
                # Rounded-corner purple background
                r, g, b, a = 99, 102, 241, 255
                # Simple corner rounding: alpha=0 in corners
                radius = size // 8
                dx = min(x, size - 1 - x)
                dy = min(y, size - 1 - y)
                if dx < radius and dy < radius:
                    dist_sq = (radius - dx) ** 2 + (radius - dy) ** 2
                    if dist_sq > radius ** 2:
                        a = 0
                row.extend([r, g, b, a])
            img_data.append(bytes(row))

        raw = zlib.compress(b"".join(img_data))

        def chunk(name: bytes, data: bytes) -> bytes:
            c = name + data
            return (
                len(data).to_bytes(4, "big")
                + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            )

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", raw)
        png += chunk(b"IEND", b"")

        with open(path, "wb") as f:
            f.write(png)

    for size in [192, 512]:
        create_simple_png(size, f"{icon_dir}/icon-{size}.png")
    print("Icons generated via fallback")


if __name__ == "__main__":
    generate_icons()
