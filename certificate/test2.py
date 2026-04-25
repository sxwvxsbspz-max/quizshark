from flask import Flask, request, send_file, Response
from PIL import Image, ImageDraw, ImageFont
import io, os
from datetime import datetime

app = Flask(__name__)

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, 'media')
FONTS_DIR = os.path.join(os.path.dirname(BASE_DIR), 'static', 'fonts')

BG_PATH    = os.path.join(MEDIA_DIR, 'certificategeneral.png')
FONT_BLACK = os.path.join(FONTS_DIR, 'Nunito-Black.ttf')
FONT_BOLD  = os.path.join(FONTS_DIR, 'Nunito-Bold.ttf')
FONT_REG   = os.path.join(FONTS_DIR, 'Nunito-Regular.ttf')

TEXT_X     = 570
IMG_W      = 1091
LINE_RIGHT = IMG_W - 55        # rechter Rand der Linie
MAX_TEXT_W = LINE_RIGHT - TEXT_X

RANK_NUM_Y   = 340
RANK_WORD_Y  = 510
SEP_Y        = 700
QUIZ_SIZE    = 38   # Schriftgröße "Quiz Urkunde"
QUIZ_GAP_BOT = 15   # Abstand: "Quiz Urkunde" → Linie
QUIZ_GAP_TOP = 10   # Abstand: Linie → "1."
RANK_GAP     = 20   # Extra-Abstand zwischen "1." und "Platz"
PLATZ_GAP    = 30   # Abstand: Unterseite "Platz" → obere Linie
NAME_GAP_TOP = 30   # Abstand: obere Linie → Name
NAME_GAP_BOT = 15   # Abstand: Name → untere Linie
DATE_GAP    = 15    # Abstand: untere Linie → Datum

LARGE_SIZE    = 155
NAME_SIZE_MAX = 120
NAME_SIZE_MIN = 36
DATE_SIZE     = 42

WHITE = (255, 255, 255)
DIM   = (190, 205, 225)

MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def _gradient_line(img, x1, x2, y,
                   color_start=(0, 210, 255), color_end=(0, 80, 200),
                   thickness=2):
    pixels = img.load()
    w = x2 - x1
    for x in range(x1, x2):
        t = (x - x1) / w
        r = int(color_start[0] + (color_end[0] - color_start[0]) * t)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * t)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * t)
        for dy in range(thickness):
            px, py = x, y + dy
            if 0 <= px < img.width and 0 <= py < img.height:
                pixels[px, py] = (r, g, b)


def _fit_font(text, font_path, max_width, start_size, min_size):
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        bbox = font.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
    return ImageFont.truetype(font_path, min_size)


def build_certificate(name, rank, date_str):
    img  = Image.open(BG_PATH).convert('RGB')
    draw = ImageDraw.Draw(img)

    font_large = _fit_font("PLATZ", FONT_BLACK, MAX_TEXT_W, 300, 50)
    font_name  = _fit_font(name, FONT_BOLD, MAX_TEXT_W, NAME_SIZE_MAX, NAME_SIZE_MIN)
    font_date  = ImageFont.truetype(FONT_REG, DATE_SIZE)
    font_quiz  = _fit_font("QUIZ URKUNDE", FONT_BOLD, MAX_TEXT_W, 300, 20)

    quiz_bbox    = font_quiz.getbbox("QUIZ URKUNDE")
    top_line_y   = RANK_NUM_Y - QUIZ_GAP_TOP
    quiz_draw_y  = top_line_y - QUIZ_GAP_BOT - quiz_bbox[3]

    rank_num_bbox  = font_large.getbbox(f"{rank}.")
    rank_draw_y    = RANK_NUM_Y - rank_num_bbox[1]
    rank_word_y    = rank_draw_y + int(rank_num_bbox[3] * 0.8) + RANK_GAP
    platz_bbox     = font_large.getbbox("PLATZ")
    sep_y          = rank_word_y + platz_bbox[3] + PLATZ_GAP

    name_bbox    = font_name.getbbox(name)
    name_draw_y  = sep_y + NAME_GAP_TOP - name_bbox[1]
    bot_line_y   = name_draw_y + name_bbox[3] + NAME_GAP_BOT + 10
    date_y       = bot_line_y + DATE_GAP

    draw.text((TEXT_X, quiz_draw_y),  "QUIZ URKUNDE", font=font_quiz, fill=WHITE)
    _gradient_line(img, TEXT_X, LINE_RIGHT, top_line_y)
    draw.text((TEXT_X, rank_draw_y),   f"{rank}.", font=font_large, fill=WHITE)
    draw.text((TEXT_X, rank_word_y),  "PLATZ",    font=font_large, fill=WHITE)
    _gradient_line(img, TEXT_X, LINE_RIGHT, sep_y)
    draw.text((TEXT_X, name_draw_y),  name,       font=font_name, fill=WHITE)
    _gradient_line(img, TEXT_X, LINE_RIGHT, bot_line_y)
    draw.text((TEXT_X, date_y),       date_str,   font=font_date, fill=DIM)

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    save_path = os.path.join(BASE_DIR, 'generatedimages', f"{timestamp}-{rank}-{name}.png")
    with open(save_path, 'wb') as f:
        f.write(buf.getvalue())
    buf.seek(0)

    return buf


HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Urkunde Vorschau</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #00167a;
      font-family: Arial, sans-serif;
    }
    .card {
      background: rgba(255,255,255,0.08);
      border: 2px solid rgba(255,255,255,0.18);
      border-radius: 20px;
      padding: 36px 32px;
      width: min(480px, 94vw);
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    h1 {
      color: #fff;
      font-size: 1.5rem;
      text-align: center;
    }
    label {
      color: rgba(255,255,255,0.8);
      font-size: 0.9rem;
      display: block;
      margin-bottom: 6px;
    }
    input {
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1.5px solid rgba(255,255,255,0.25);
      background: rgba(255,255,255,0.1);
      color: #fff;
      font-size: 1rem;
    }
    input[type=date]::-webkit-calendar-picker-indicator { filter: invert(1); }
    button {
      padding: 14px;
      border-radius: 12px;
      border: none;
      background: rgba(255,255,255,0.2);
      color: #fff;
      font-size: 1.1rem;
      font-weight: bold;
      cursor: pointer;
    }
    button:hover { background: rgba(255,255,255,0.3); }
  </style>
</head>
<body>
  <form class="card" method="get" action="/vorschau" target="_blank">
    <h1>Urkunde Vorschau</h1>
    <div>
      <label>Name</label>
      <input type="text" name="name" value="Max Mustermann" required>
    </div>
    <div>
      <label>Rang</label>
      <input type="number" name="rang" value="1" min="1" required>
    </div>
    <div>
      <label>Datum</label>
      <input type="date" name="datum" value="{today}" required>
    </div>
    <button type="submit">Vorschau generieren</button>
  </form>
</body>
</html>
""".replace("{today}", datetime.now().strftime("%Y-%m-%d"))


@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')


@app.route('/vorschau')
def vorschau():
    name  = request.args.get('name', 'Spieler').strip() or 'Spieler'
    rang  = int(request.args.get('rang', 1) or 1)
    datum = request.args.get('datum', '')

    if datum:
        try:
            d = datetime.strptime(datum, '%Y-%m-%d')
            date_str = f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"
        except ValueError:
            date_str = datum
    else:
        today = datetime.now()
        date_str = f"{today.day}. {MONTHS_DE[today.month - 1]} {today.year}"

    buf = build_certificate(name=name, rank=rang, date_str=date_str)
    return send_file(buf, mimetype='image/png')


if __name__ == '__main__':
    print("Urkunde-Vorschau läuft auf http://0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080, debug=False)
