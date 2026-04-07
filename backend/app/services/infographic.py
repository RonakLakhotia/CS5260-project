"""Programmatic infographic generator using Pillow.

Generates clean, readable educational slides from planner concept data.
No AI image generation — all text is rendered exactly as written.
"""
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

# Slide dimensions (9:16 vertical for YouTube Shorts)
WIDTH = 1080
HEIGHT = 1920

# Colors
BG_TOP = (15, 23, 42)        # dark navy
BG_BOTTOM = (30, 41, 59)     # slightly lighter navy
ACCENT = (56, 189, 248)      # cyan
ACCENT_DIM = (30, 100, 140)  # dimmed cyan
WHITE = (255, 255, 255)
LIGHT_GRAY = (203, 213, 225)
DARK_CARD = (30, 41, 59, 200)
CARD_BG = (51, 65, 85)


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a system font. Tries common macOS/Linux paths, falls back to default."""
    font_paths = [
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
    ]

    for path in font_paths:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    return ImageFont.load_default()


def _draw_gradient_bg(draw: ImageDraw.Draw):
    """Draw a vertical gradient background."""
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def _draw_rounded_rect(draw: ImageDraw.Draw, xy: tuple, fill: tuple, radius: int = 20):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _draw_accent_line(draw: ImageDraw.Draw, y: int, width: int = 200):
    """Draw a horizontal accent line."""
    x_start = (WIDTH - width) // 2
    draw.line([(x_start, y), (x_start + width, y)], fill=ACCENT, width=3)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def generate_overview_slide(concept: dict, slide_num: int, total_slides: int) -> Image.Image:
    """Generate an overview slide for a concept.

    Shows: concept title, description, key timestamp range.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw)

    # Fonts
    font_title = _get_font(64, bold=True)
    font_subtitle = _get_font(32)
    font_body = _get_font(36)
    font_small = _get_font(28)
    font_label = _get_font(24)

    y = 120

    # Slide counter
    counter_text = f"{slide_num} / {total_slides}"
    draw.text((WIDTH - 150, 60), counter_text, fill=LIGHT_GRAY, font=font_small)

    # Top accent line
    _draw_accent_line(draw, y, 100)
    y += 30

    # "KEY CONCEPT" label
    draw.text((WIDTH // 2, y), "KEY CONCEPT", fill=ACCENT, font=font_label, anchor="mt")
    y += 60

    # Title
    title = concept.get("title", "Untitled")
    title_lines = _wrap_text(title.upper(), font_title, WIDTH - 160)
    for line in title_lines:
        draw.text((WIDTH // 2, y), line, fill=WHITE, font=font_title, anchor="mt")
        y += 80
    y += 20

    # Accent line under title
    _draw_accent_line(draw, y, 300)
    y += 50

    # Description
    description = concept.get("description", "")
    if description:
        desc_lines = _wrap_text(description, font_body, WIDTH - 160)
        for line in desc_lines:
            draw.text((WIDTH // 2, y), line, fill=LIGHT_GRAY, font=font_body, anchor="mt")
            y += 50
    y += 40

    # Timestamp card
    start = concept.get("start_time", 0)
    end = concept.get("end_time", 0)
    start_fmt = f"{int(start // 60)}:{int(start % 60):02d}"
    end_fmt = f"{int(end // 60)}:{int(end % 60):02d}"

    card_y = y
    _draw_rounded_rect(draw, (80, card_y, WIDTH - 80, card_y + 120), fill=CARD_BG)
    draw.text((WIDTH // 2, card_y + 25), "TIMESTAMP RANGE", fill=ACCENT, font=font_label, anchor="mt")
    draw.text((WIDTH // 2, card_y + 70), f"{start_fmt}  —  {end_fmt}", fill=WHITE, font=font_subtitle, anchor="mt")
    y = card_y + 160

    # Key points from segments
    segments = concept.get("segments", [])
    if segments:
        y += 20
        draw.text((80, y), "KEY POINTS", fill=ACCENT, font=font_label)
        y += 50

        # Extract a few short sentences from segments as key points
        all_text = " ".join(s.get("text", "") for s in segments[:3])
        sentences = [s.strip() for s in all_text.replace(".", ".\n").split("\n") if len(s.strip()) > 20]

        for i, sentence in enumerate(sentences[:4]):
            if y > HEIGHT - 200:
                break
            # Bullet point card
            _draw_rounded_rect(draw, (80, y, WIDTH - 80, y + 100), fill=CARD_BG)
            bullet = f"  {sentence[:70]}{'...' if len(sentence) > 70 else ''}"
            draw.text((100, y + 30), f"→", fill=ACCENT, font=font_body)
            point_lines = _wrap_text(sentence[:80], font_small, WIDTH - 240)
            for j, pl in enumerate(point_lines[:2]):
                draw.text((150, y + 20 + j * 35), pl, fill=WHITE, font=font_small)
            y += 110

    # Footer
    draw.text((WIDTH // 2, HEIGHT - 80), "YTSage — AI Video Summarizer", fill=ACCENT_DIM, font=font_label, anchor="mt")

    return img


def generate_detail_slide(concept: dict, slide_num: int, total_slides: int) -> Image.Image:
    """Generate a detail/deep-dive slide for a concept.

    Shows: concept title, detailed transcript excerpts with timestamps.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    _draw_gradient_bg(draw)

    # Fonts
    font_title = _get_font(48, bold=True)
    font_body = _get_font(32)
    font_small = _get_font(28)
    font_label = _get_font(24)
    font_timestamp = _get_font(22)

    y = 100

    # Slide counter
    counter_text = f"{slide_num} / {total_slides}"
    draw.text((WIDTH - 150, 60), counter_text, fill=LIGHT_GRAY, font=font_small)

    # "DEEP DIVE" label
    draw.text((WIDTH // 2, y), "DEEP DIVE", fill=ACCENT, font=font_label, anchor="mt")
    y += 50

    # Title
    title = concept.get("title", "Untitled")
    title_lines = _wrap_text(title, font_title, WIDTH - 160)
    for line in title_lines:
        draw.text((WIDTH // 2, y), line, fill=WHITE, font=font_title, anchor="mt")
        y += 60
    y += 10

    _draw_accent_line(draw, y, 200)
    y += 40

    # Show transcript excerpts with timestamps
    segments = concept.get("segments", [])
    for i, seg in enumerate(segments):
        if y > HEIGHT - 200:
            break

        start = seg.get("start_time", 0)
        start_fmt = f"{int(start // 60)}:{int(start % 60):02d}"
        text = seg.get("text", "")

        # Timestamp badge
        _draw_rounded_rect(draw, (80, y, 200, y + 40), fill=ACCENT)
        draw.text((140, y + 20), start_fmt, fill=BG_TOP, font=font_timestamp, anchor="mm")

        # Dotted line connector
        if i < len(segments) - 1 and y + 250 < HEIGHT - 200:
            for dot_y in range(y + 50, y + 250, 10):
                draw.rectangle([(138, dot_y), (142, dot_y + 4)], fill=ACCENT_DIM)

        y += 50

        # Excerpt card
        excerpt = text[:200] + ("..." if len(text) > 200 else "")
        card_height = 30
        excerpt_lines = _wrap_text(excerpt, font_small, WIDTH - 200)
        card_height += len(excerpt_lines[:4]) * 38

        _draw_rounded_rect(draw, (80, y, WIDTH - 80, y + card_height + 20), fill=CARD_BG)
        for j, line in enumerate(excerpt_lines[:4]):
            draw.text((110, y + 15 + j * 38), line, fill=LIGHT_GRAY, font=font_small)

        y += card_height + 40

    # Footer
    draw.text((WIDTH // 2, HEIGHT - 80), "YTSage — AI Video Summarizer", fill=ACCENT_DIM, font=font_label, anchor="mt")

    return img


def generate_infographics(concepts: list[dict], output_dir: str) -> list[str]:
    """Generate all infographic slides for the given concepts.

    Args:
        concepts: List of concept dicts from the planner
        output_dir: Directory to save PNG files

    Returns:
        List of file paths to generated slides
    """
    os.makedirs(output_dir, exist_ok=True)

    total_slides = len(concepts) * 2  # 2 slides per concept
    paths = []

    for i, concept in enumerate(concepts):
        # Slide 1: Overview
        slide_num = i * 2 + 1
        overview = generate_overview_slide(concept, slide_num, total_slides)
        path1 = os.path.join(output_dir, f"slide_{slide_num:02d}_overview.png")
        overview.save(path1, "PNG")
        paths.append(path1)
        print(f"    Generated overview slide for '{concept.get('title', '')}'")

        # Slide 2: Detail
        slide_num = i * 2 + 2
        detail = generate_detail_slide(concept, slide_num, total_slides)
        path2 = os.path.join(output_dir, f"slide_{slide_num:02d}_detail.png")
        detail.save(path2, "PNG")
        paths.append(path2)
        print(f"    Generated detail slide for '{concept.get('title', '')}'")

    return paths
