#!/usr/bin/env python3
"""
Icon-Generator für TV Remote PWA

Dieses Skript generiert PNG-Icons aus der SVG-Vorlage.

Installation der Abhängigkeiten:
    pip install cairosvg pillow

Alternativ mit ImageMagick:
    brew install imagemagick  # macOS
    convert app/static/icons/icon.svg -resize 180x180 app/static/icons/apple-touch-icon.png

Oder online:
    https://realfavicongenerator.net/
"""
import os
import sys

ICON_SIZES = [16, 32, 72, 96, 128, 144, 152, 180, 192, 384, 512]
ICONS_DIR = os.path.join(os.path.dirname(__file__), 'app', 'static', 'icons')
SVG_FILE = os.path.join(ICONS_DIR, 'icon.svg')


def generate_with_cairosvg():
    """Generate PNGs using CairoSVG"""
    try:
        import cairosvg
    except ImportError:
        print("CairoSVG nicht installiert. Installiere mit: pip install cairosvg")
        return False

    for size in ICON_SIZES:
        output_file = os.path.join(ICONS_DIR, f'icon-{size}x{size}.png')
        cairosvg.svg2png(
            url=SVG_FILE,
            write_to=output_file,
            output_width=size,
            output_height=size
        )
        print(f"Erstellt: {output_file}")

    # Apple Touch Icon (180x180)
    cairosvg.svg2png(
        url=SVG_FILE,
        write_to=os.path.join(ICONS_DIR, 'apple-touch-icon.png'),
        output_width=180,
        output_height=180
    )

    # Favicons
    cairosvg.svg2png(
        url=SVG_FILE,
        write_to=os.path.join(ICONS_DIR, 'favicon-32x32.png'),
        output_width=32,
        output_height=32
    )
    cairosvg.svg2png(
        url=SVG_FILE,
        write_to=os.path.join(ICONS_DIR, 'favicon-16x16.png'),
        output_width=16,
        output_height=16
    )

    print("\nAlle Icons erfolgreich erstellt!")
    return True


def generate_simple_fallback():
    """Generate icons with 'TV' text using Pillow"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow nicht installiert. Installiere mit: pip install Pillow")
        return False

    # Colors from the design
    bg_color_top = (26, 26, 46)  # #1a1a2e
    bg_color_bottom = (15, 15, 26)  # #0f0f1a
    accent_color = (79, 70, 229)  # #4f46e5

    def create_icon(size):
        """Create a single icon at the specified size"""
        img = Image.new('RGB', (size, size), bg_color_bottom)
        draw = ImageDraw.Draw(img)

        # Create gradient background
        for y in range(size):
            ratio = y / size
            r = int(bg_color_top[0] * (1 - ratio) + bg_color_bottom[0] * ratio)
            g = int(bg_color_top[1] * (1 - ratio) + bg_color_bottom[1] * ratio)
            b = int(bg_color_top[2] * (1 - ratio) + bg_color_bottom[2] * ratio)
            draw.line([(0, y), (size, y)], fill=(r, g, b))

        # Draw rounded corners mask
        corner_radius = size // 5
        mask = Image.new('L', (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, size, size], radius=corner_radius, fill=255)

        # Apply mask
        background = Image.new('RGB', (size, size), (0, 0, 0))
        img = Image.composite(img, background, mask)

        draw = ImageDraw.Draw(img)

        # Draw "TV" text
        font_size = int(size * 0.45)
        font = None

        # List of font paths to try
        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]

        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except (OSError, IOError):
                continue

        if font is None:
            # Use default font
            font = ImageFont.load_default()

        text = "TV"

        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (size - text_width) // 2
            y = (size - text_height) // 2 - bbox[1]
        except Exception:
            # Fallback for older Pillow or font issues
            text_width = font_size * len(text) * 0.6
            text_height = font_size
            x = (size - text_width) // 2
            y = (size - text_height) // 2

        draw.text((x, y), text, font=font, fill=accent_color)

        return img

    for size in ICON_SIZES:
        img = create_icon(size)
        output_file = os.path.join(ICONS_DIR, f'icon-{size}x{size}.png')
        img.save(output_file, 'PNG')
        print(f"Erstellt: {output_file}")

    # Create apple-touch-icon and favicons
    for name, size in [('apple-touch-icon.png', 180),
                       ('favicon-32x32.png', 32),
                       ('favicon-16x16.png', 16)]:
        img = create_icon(size)
        img.save(os.path.join(ICONS_DIR, name), 'PNG')
        print(f"Erstellt: {name}")

    print("\nAlle Icons erfolgreich erstellt!")
    return True


if __name__ == '__main__':
    print("TV Remote Icon Generator")
    print("=" * 40)

    if not os.path.exists(SVG_FILE):
        print(f"Fehler: SVG-Vorlage nicht gefunden: {SVG_FILE}")
        sys.exit(1)

    # Try CairoSVG first (better quality)
    if not generate_with_cairosvg():
        print("\nVersuche Fallback mit Pillow...")
        if not generate_simple_fallback():
            print("\nKeine Icon-Bibliothek verfügbar!")
            print("Bitte installiere: pip install cairosvg")
            print("Oder: pip install Pillow")
            sys.exit(1)
