from PIL import Image, ImageDraw, ImageFont
import io
import os
from datetime import datetime

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, 'media')
FONTS_DIR = os.path.join(os.path.dirname(BASE_DIR), 'static', 'fonts')

BG_PATH    = os.path.join(MEDIA_DIR, 'certificategeneral.png')
FONT_BLACK = os.path.join(FONTS_DIR, 'Nunito-Black.ttf')
FONT_BOLD  = os.path.join(FONTS_DIR, 'Nunito-Bold.ttf')
FONT_REG   = os.path.join(FONTS_DIR, 'Nunito-Regular.ttf')

# ── Positionen (Pixel, Basis: 1091 × 1441) ───────────────────────────────────
TEXT_X     = 400          # linker Rand des Textblocks (rechte Bildhälfte)
IMG_W      = 1091
MAX_TEXT_W = IMG_W - TEXT_X - 25   # ~666 px verfügbare Breite

RANK_NUM_Y  = 340   # "1."
RANK_WORD_Y = 510   # "Platz"
SEP_Y       = 700   # Trennlinie
NAME_Y      = 735   # Spielername
DATE_Y      = 835   # Datum

LARGE_SIZE    = 155
NAME_SIZE_MAX = 70
NAME_SIZE_MIN = 36
DATE_SIZE     = 42

WHITE = (255, 255, 255)
DIM   = (190, 205, 225)

MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _fit_font(text, font_path, max_width, start_size, min_size):
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
    return ImageFont.truetype(font_path, min_size)


def generate_certificate(name: str, rank: int) -> bytes:
    img  = Image.open(BG_PATH).convert('RGB')
    draw = ImageDraw.Draw(img)

    font_large = ImageFont.truetype(FONT_BLACK, LARGE_SIZE)
    font_name  = _fit_font(name, FONT_BOLD, MAX_TEXT_W, NAME_SIZE_MAX, NAME_SIZE_MIN)
    font_date  = ImageFont.truetype(FONT_REG, DATE_SIZE)

    draw.text((TEXT_X, RANK_NUM_Y),  f"{rank}.", font=font_large, fill=WHITE)
    draw.text((TEXT_X, RANK_WORD_Y), "Platz",    font=font_large, fill=WHITE)

    draw.line([(TEXT_X, SEP_Y), (IMG_W - 25, SEP_Y)], fill=WHITE, width=2)

    draw.text((TEXT_X, NAME_Y), name, font=font_name, fill=WHITE)

    today    = datetime.now()
    date_str = f"{today.day}. {MONTHS_DE[today.month - 1]} {today.year}"
    draw.text((TEXT_X, DATE_Y), date_str, font=font_date, fill=DIM)

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf.read()
