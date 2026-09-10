"""PNG-карточка расписания для Telegram (Pillow).

Рисует тёмную карточку ~1080px шириной: заголовок (группа/преподаватель + дата),
далее полосы пар: номер/время, предмет, подгруппа, аудитория, (преподаватель
для групп / группа для преподавателей). Возвращает bytes для sendPhoto.
"""
import io
import logging
from datetime import date

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


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(FONT_DIR + name, size)
    except Exception:
        return ImageFont.load_default()


def render_schedule_card(title: str, date_str: str, lessons: list,
                         extra_field: str = "") -> bytes | None:
    """lessons: [{pair, subgroup, subject, room, teacher?, group?}, ...]"""
    try:
        rows = list(lessons)
        header_h = 190
        row_h = 150
        empty_h = 160
        height = header_h + (len(rows) * row_h if rows else empty_h) + PAD

        img = Image.new("RGB", (W, height), BG)
        d = ImageDraw.Draw(img)

        # ── шапка ────────────────────────────────────────────────
        f_title = _font(52, bold=True)
        f_date  = _font(34)
        d.text((PAD, 46), title, font=f_title, fill=ACCENT)
        d.text((PAD, 118), date_str, font=f_date, fill=MUTED)
        d.line([(PAD, 176), (W - PAD, 176)], fill=CARD, width=3)

        # ── пары ─────────────────────────────────────────────────
        y = header_h + 10
        if not rows:
            d.text((PAD, y + 30), "📭 Занятий нет", font=_font(44), fill=MUTED)
        else:
            f_pair  = _font(36, bold=True)
            f_subj  = _font(40, bold=True)
            f_meta  = _font(30)
            for l in rows:
                pair = str(l.get("pair", ""))
                time = l.get("time", "")
                subg = f" · пг {l['subgroup']}" if l.get("subgroup") else ""
                room = l.get("room") or "—"
                extra = l.get(extra_field, "") if extra_field else ""

                # полоса-фон
                d.rounded_rectangle([(PAD - 12, y), (W - PAD + 12, y + row_h - 24)],
                                    radius=18, fill=CARD)
                # левая метка пары
                d.text((PAD + 12, y + 18), pair, font=_font(34, bold=True), fill=ACCENT)
                if time:
                    d.text((PAD + 12 + (44 if len(pair) == 1 else 74), y + 22),
                           time, font=_font(26), fill=MUTED)
                # предмет
                d.text((PAD + 250, y + 16), l.get("subject", ""), font=f_subj, fill=TEXT)
                # мета-строка
                meta = f"ауд. {room}" if room not in ("—", "") else "ауд. —"
                if subg:
                    meta += subg
                if extra:
                    meta += f"   ·   {extra}"
                d.text((PAD + 250, y + 70), meta, font=f_meta, fill=MUTED)
                y += row_h

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error("render_schedule_card failed: %s", e)
        return None
