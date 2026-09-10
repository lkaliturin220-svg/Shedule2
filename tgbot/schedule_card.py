"""PNG-карточка расписания v2 — редизайн.

Что изменилось к v1:
- Время вынесено в компактную «пилюлю», номер пары — крупный маркер слева на
  цветном языке акцента
- Больше воздуха: отступы 56, межстрочные интервалы, высота строки по контенту
- Тонкая акцентная полоска слева каждой карточки пары
- Мета-строка: аудитория как «пилюля», преподаватель отдельно серым
- Заголовок: группа крупно, дата под ним, сверху маленький оверлайн «РАСПИСАНИЕ»
- Сглаженные скругления 20px, фон чуть светлее для контраста карточек
"""
import io
import logging

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

W = 1080
PAD = 56
BG      = (13, 20, 38)     # фон глубже
CARD    = (26, 35, 58)     # карточки
CARD_L  = (34, 46, 74)     # пилюли внутри
ACCENT  = (45, 212, 191)   # teal-400
ACCENT_D= (17, 138, 125)   # teal-600 (полоса)
TEXT    = (235, 240, 248)
MUTED   = (146, 158, 178)
FAINT   = (96, 108, 128)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

PAIR_TIMES = {
    1: "08:30–10:00", 2: "10:20–11:50", 3: "12:10–13:40",
    4: "14:00–15:30", 5: "15:40–17:10", 6: "17:15–18:45",
    7: "19:00–20:30", 8: "20:00–21:30",
}


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(FONT_DIR + name, size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def render_schedule_card(title: str, date_str: str, lessons: list,
                         extra_field: str = "") -> bytes | None:
    """lessons: [{pair, time?, subgroup, subject, room, teacher?, group?}, ...]"""
    try:
        tmp = Image.new("RGB", (10, 10))
        td = ImageDraw.Draw(tmp)

        f_over  = _font(26, bold=True)
        f_title = _font(56, bold=True)
        f_date  = _font(32)
        f_num   = _font(46, bold=True)
        f_time  = _font(27, bold=True)
        f_subj  = _font(38, bold=True)
        f_meta  = _font(29)

        title_lines = _wrap(td, title, f_title, W - PAD * 2 - 10)
        date_lines  = _wrap(td, date_str, f_date, W - PAD * 2 - 10)

        header_h = 64 + 34 + len(title_lines) * 62 + len(date_lines) * 42 + 46

        LEFT_W = 235                      # колонка номера/времени
        tx = PAD + LEFT_W                 # правая колонка
        subj_max_w = W - tx - PAD - 24
        meta_max_w = subj_max_w - 8

        prepared = []
        for l in lessons:
            pair = str(l.get("pair", ""))
            time = l.get("time") or PAIR_TIMES.get(l.get("pair"), "")
            subg = f" · пг {l['subgroup']}" if l.get("subgroup") else ""
            room = l.get("room") or "—"
            extra = l.get(extra_field, "") if extra_field else ""
            meta = f"ауд. {room}" + subg + (f"  ·  {extra}" if extra else "")
            subj_lines = _wrap(td, l.get("subject", ""), f_subj, subj_max_w)
            meta_lines = _wrap(td, meta, f_meta, meta_max_w)
            body_h = len(subj_lines) * 50 + 12 + len(meta_lines) * 38
            row_h = max(132, body_h + 44)
            prepared.append({"pair": pair, "time": time, "subj": subj_lines,
                             "meta": meta_lines, "row_h": row_h})

        gap = 20
        height = header_h + (sum(p["row_h"] for p in prepared)
                             + gap * max(0, len(prepared) - 1) if prepared else 150) \
            + 30 + PAD
        img = Image.new("RGB", (W, height), BG)
        d = ImageDraw.Draw(img)

        # ── шапка ────────────────────────────────────────────────
        d.text((PAD, 46), "РАСПИСАНИЕ", font=f_over, fill=ACCENT_D)
        y = 46 + 40
        for line in title_lines:
            d.text((PAD, y), line, font=f_title, fill=TEXT)
            y += 62
        for line in date_lines:
            d.text((PAD, y + 4), line, font=f_date, fill=MUTED)
            y += 42

        d.line([(PAD, header_h - 26), (W - PAD, header_h - 26)], fill=(28, 38, 60), width=2)

        # ── пары ─────────────────────────────────────────────────
        y = header_h + 6
        if not prepared:
            d.text((PAD, y + 30), "Занятий нет", font=_font(42), fill=MUTED)
        for p in prepared:
            rh = p["row_h"]
            # карточка
            d.rounded_rectangle([(PAD - 8, y), (W - PAD + 8, y + rh)],
                                radius=20, fill=CARD)
            # акцентная полоска слева
            d.rounded_rectangle([(PAD - 8, y), (PAD - 1, y + rh)],
                                radius=4, fill=ACCENT_D)
            # номер пары
            d.text((PAD + 24, y + 24), p["pair"], font=f_num, fill=ACCENT)
            # время-пилюля под номером
            if p["time"]:
                tw = td.textlength(p["time"], font=f_time)
                px, py = PAD + 14, y + 84
                d.rounded_rectangle([(px, py), (px + tw + 26, py + 40)],
                                    radius=20, fill=CARD_L)
                d.text((px + 13, py + 6), p["time"], font=f_time, fill=MUTED)
            # предмет
            ty = y + 26
            for line in p["subj"]:
                d.text((tx, ty), line, font=f_subj, fill=TEXT)
                ty += 50
            ty += 10
            for line in p["meta"]:
                d.text((tx, ty), line, font=f_meta, fill=MUTED)
                ty += 38
            y += rh + gap

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error("render_schedule_card failed: %s", e)
        return None
