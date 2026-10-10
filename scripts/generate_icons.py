import os
from pathlib import Path
from PIL import Image, ImageDraw

def generate_icons():
    project_root = Path(__file__).parent.parent.resolve()
    assets_dir = project_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate high-res 512x512 base icon
    size = 512
    img = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded background with modern dark gradient feel
    margin = 32
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=96,
        fill=(15, 23, 42, 255),  # Slate 900
        outline=(51, 65, 85, 255),  # Slate 700
        width=6
    )

    # Shield polygon coordinates (scaled to 512)
    shield_pts = [
        (256, 96),   # top center
        (400, 160),  # top right
        (400, 310),  # mid right
        (256, 426),  # bottom point
        (112, 310),  # mid left
        (112, 160),  # top left
    ]
    # Draw outer glow / shadow
    draw.polygon(shield_pts, fill=(14, 165, 233, 255), outline=(2, 132, 199, 255))

    # Inner shield accent
    inner_shield_pts = [
        (256, 124),
        (376, 180),
        (376, 296),
        (256, 396),
        (136, 296),
        (136, 180),
    ]
    draw.polygon(inner_shield_pts, fill=(56, 189, 248, 255))

    # Checkmark inside shield
    draw.line(
        [(192, 256), (240, 304), (324, 204)],
        fill=(255, 255, 255, 255),
        width=30,
        joint="curve"
    )

    # Save PNG
    png_path = assets_dir / "icon.png"
    img.save(png_path, format="PNG")
    print(f"Generated {png_path}")

    # 2. Save multi-size ICO for Windows
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_path = assets_dir / "icon.ico"
    img.save(ico_path, format="ICO", sizes=ico_sizes)
    print(f"Generated {ico_path}")

    # 3. Also generate small sizes for tray / desktop if needed
    tray_img = img.resize((64, 64), Image.Resampling.LANCZOS)
    tray_path = assets_dir / "tray_icon.png"
    tray_img.save(tray_path, format="PNG")
    print(f"Generated {tray_path}")

if __name__ == "__main__":
    generate_icons()
