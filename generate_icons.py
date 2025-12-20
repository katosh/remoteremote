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
    """Generate PNGs using CairoSVG with transparent background"""
    try:
        import cairosvg
        from PIL import Image
        import io
    except ImportError:
        print("CairoSVG oder Pillow nicht installiert. Installiere mit: pip install cairosvg Pillow")
        return False

    # Read SVG content
    with open(SVG_FILE, 'r') as f:
        svg_content = f.read()

    for size in ICON_SIZES:
        output_file = os.path.join(ICONS_DIR, f'icon-{size}x{size}.png')
        # Convert SVG to PNG with transparency
        png_data = cairosvg.svg2png(
            bytestring=svg_content.encode('utf-8'),
            output_width=size,
            output_height=size
        )
        # Ensure PNG has proper alpha channel
        img = Image.open(io.BytesIO(png_data))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        img.save(output_file, 'PNG')
        print(f"Erstellt: {output_file}")

    # Apple Touch Icon (180x180)
    png_data = cairosvg.svg2png(
        bytestring=svg_content.encode('utf-8'),
        output_width=180,
        output_height=180
    )
    img = Image.open(io.BytesIO(png_data))
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    img.save(os.path.join(ICONS_DIR, 'apple-touch-icon.png'), 'PNG')

    # Favicons
    for size, name in [(32, 'favicon-32x32.png'), (16, 'favicon-16x16.png')]:
        png_data = cairosvg.svg2png(
            bytestring=svg_content.encode('utf-8'),
            output_width=size,
            output_height=size
        )
        img = Image.open(io.BytesIO(png_data))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        img.save(os.path.join(ICONS_DIR, name), 'PNG')

    # Generate favicon.ico with multiple sizes
    generate_ico()

    print("\nAlle Icons erfolgreich erstellt!")
    return True


def generate_ico():
    """Generate favicon.ico with multiple sizes (16, 32, 48)"""
    try:
        from PIL import Image
    except ImportError:
        print("Pillow nicht installiert für ICO-Generierung")
        return

    ico_sizes = [16, 32, 48]
    images = []

    for size in ico_sizes:
        icon_path = os.path.join(ICONS_DIR, f'icon-{size}x{size}.png')
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            images.append(img.copy())
        else:
            # Use closest available size and resize
            for available_size in sorted(ICON_SIZES):
                if available_size >= size:
                    icon_path = os.path.join(ICONS_DIR, f'icon-{available_size}x{available_size}.png')
                    if os.path.exists(icon_path):
                        img = Image.open(icon_path)
                        if img.mode != 'RGBA':
                            img = img.convert('RGBA')
                        resized = img.resize((size, size), Image.LANCZOS)
                        images.append(resized)
                        break

    if images:
        ico_path = os.path.join(ICONS_DIR, 'favicon.ico')
        # Save ICO - use the largest image as base
        largest = max(images, key=lambda x: x.width)
        others = [img for img in images if img is not largest]
        largest.save(
            ico_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in images],
            append_images=others
        )
        print(f"Erstellt: {ico_path}")


def generate_simple_fallback():
    """Generate icons with 'TV' text using Pillow with transparent corners"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow nicht installiert. Installiere mit: pip install Pillow")
        return False

    # Colors from the design (with alpha)
    bg_color_top = (26, 26, 46, 255)  # #1a1a2e
    bg_color_bottom = (15, 15, 26, 255)  # #0f0f1a
    accent_color = (79, 70, 229, 255)  # #4f46e5

    def create_master_icon():
        """Create a high-resolution master icon (2048x2048) for scaling down"""
        master_size = 2048

        # Create a temporary RGB image for the gradient at high resolution
        gradient_img = Image.new('RGB', (master_size, master_size), bg_color_bottom[:3])
        gradient_draw = ImageDraw.Draw(gradient_img)

        # Create gradient background
        for y in range(master_size):
            ratio = y / master_size
            r = int(bg_color_top[0] * (1 - ratio) + bg_color_bottom[0] * ratio)
            g = int(bg_color_top[1] * (1 - ratio) + bg_color_bottom[1] * ratio)
            b = int(bg_color_top[2] * (1 - ratio) + bg_color_bottom[2] * ratio)
            gradient_draw.line([(0, y), (master_size, y)], fill=(r, g, b))

        # Convert gradient to RGBA
        gradient_rgba = gradient_img.convert('RGBA')

        # Create rounded corners mask (radius = 1/5 of size, matching SVG rx=96 at 512)
        corner_radius = master_size // 5
        mask = Image.new('L', (master_size, master_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, master_size - 1, master_size - 1], radius=corner_radius, fill=255)

        # Apply mask to gradient - this makes corners transparent
        gradient_rgba.putalpha(mask)

        # Draw "TV" text
        draw = ImageDraw.Draw(gradient_rgba)
        font_size = int(master_size * 0.45)
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
            x = (master_size - text_width) // 2
            y = (master_size - text_height) // 2 - bbox[1]
        except Exception:
            # Fallback for older Pillow or font issues
            text_width = font_size * len(text) * 0.6
            text_height = font_size
            x = (master_size - text_width) // 2
            y = (master_size - text_height) // 2

        draw.text((x, y), text, font=font, fill=accent_color)

        return gradient_rgba

    # Create master high-res icon once
    print("Erstelle Master-Icon (2048x2048)...")
    master_icon = create_master_icon()

    # Scale down for all sizes
    for size in ICON_SIZES:
        img = master_icon.resize((size, size), Image.LANCZOS)
        output_file = os.path.join(ICONS_DIR, f'icon-{size}x{size}.png')
        img.save(output_file, 'PNG')
        print(f"Erstellt: {output_file}")

    # Create apple-touch-icon and favicons
    for name, size in [('apple-touch-icon.png', 180),
                       ('favicon-32x32.png', 32),
                       ('favicon-16x16.png', 16)]:
        img = master_icon.resize((size, size), Image.LANCZOS)
        img.save(os.path.join(ICONS_DIR, name), 'PNG')
        print(f"Erstellt: {name}")

    # Generate favicon.ico
    generate_ico()

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
