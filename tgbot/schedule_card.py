"""PNG-карточка расписания для Telegram (Pillow).

Тёмная карточка: шапка (группа/преподаватель + дата), полосы пар.
Длинные тексты переносятся по словам, высота строки растёт автоматически —
ничего не обрезается.
"""
import io
import logging

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

W = 1080
PAD = 48
BG      = (15, 23, 42)     # slate-900
CARD    = (30, 41, 59)     # slate-800
ACCENT  = (45, 212, 191)   # teal-400
TEXT    = (226, 232, 240)  # slate-200
MUTED   = (148, 163, 184)  # slate-400

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
    """Перенос по словам: строка ломается, пока влезает в max_w."""
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

        f_title = _font(52, bold=True)
        f_date  = _font(34)
        f_pair  = _font(36, bold=True)
        f_time  = _font(26)
        f_subj  = _font(40, bold=True)
        f_meta  = _font(30)

        title_lines = _wrap(td, title, f_title, W - PAD * 2)

        header_h = 60 + len(title_lines) * 60 + 60

        # предрасчёт высоты каждой строки пары
        subj_max_w = W - PAD * 2 - 250
        meta_max_w = subj_max_w
        prepared = []
        for l in lessons:
            pair = str(l.get("pair", ""))
            time = l.get("time") or PAIR_TIMES.get(l.get("pair"), "")
            subg = f" · пг {l['subgroup']}" if l.get("subgroup") else ""
            room = l.get("room") or "—"
            extra = l.get(extra_field, "") if extra_field else ""
            meta = f"ауд. {room}" + subg + (f"   ·   {extra}" if extra else "")
            subj_lines = _wrap(td, l.get("subject", ""), f_subj, subj_max_w)
            meta_lines = _wrap(td, meta, f_meta, meta_max_w)
            body_h = len(subj_lines) * 48 + len(meta_lines) * 40 + 26
            row_h = max(120, body_h)
            prepared.append({"pair": pair, "time": time, "subj": subj_lines,
                             "meta": meta_lines, "row_h": row_h})

        height = header_h + sum(p["row_h"] + 18 for p in prepared or []) + PAD \
            + (120 if not prepared else 0)
        img = Image.new("RGB", (W, height), BG)
        d = ImageDraw.Draw(img)

        # ── шапка ────────────────────────────────────────────────
        y = 46
        for line in title_lines:
            d.text((PAD, y), line, font=f_title, fill=ACCENT)
            y += 60
        d.text((PAD, y + 8), date_str, font=f_date, fill=MUTED)
        d.line([(PAD, header_h - 20), (W - PAD, header_h - 20)], fill=CARD, width=3)

        # ── пары ─────────────────────────────────────────────────
        y = header_h + 10
        if not prepared:
            d.text((PAD, y + 30), "Занятий нет", font=_font(44), fill=MUTED)
        for p in prepared:
            rh = p["row_h"]
            d.rounded_rectangle([(PAD - 12, y), (W - PAD + 12, y + rh - 10)],
                                radius=18, fill=CARD)
            # левая колонка: номер пары + время
            d.text((PAD + 16, y + 20), p["pair"], font=f_pair, fill=ACCENT)
            if p["time"]:
                d.text((PAD + 16, y + 66), p["time"], font=f_time, fill=MUTED)
            # правая колонка: предмет (перенос) + мета (перенос)
            tx = PAD + 190
            ty = y + 16
            for line in p["subj"]:
                d.text((tx, ty), line, font=f_subj, fill=TEXT)
                ty += 48
            ty += 4
            for line in p["meta"]:
                d.text((tx, ty), line, font=f_meta, fill=MUTED)
                ty += 40
            y += rh + 18

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error("render_schedule_card failed: %s", e)
        return None
