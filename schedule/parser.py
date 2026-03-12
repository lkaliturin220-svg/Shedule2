"""
Парсер файлов расписания формата studentam_DD.MM.YYYY.xlsx

Структура файла:
  Строка 1:  «Расписание на ДД.ММ.ГГГГ»  (название листа = день недели)
  Строка 2:  Пара | Дисциплина | Ауд.  (заголовки, повторяются на 4 группы)
  Строка 3:  Преподаватель (повторяется)
  Строка 4:  Номера подгрупп 1/2/3
  Строка 5:  Имена групп (1ИСИП-25-9, 1ОГР-25-9, ...)

Далее блоки:
  - строка с именами групп (col 1,7,13,19)
  - строки пар: col[0]=номер пары, далее блоки по 6 колонок
  - следующая строка = преподаватели

Каждый блок (6 колонок, смещения от col):
  +0 : дисциплина подгруппа-1 (или вся группа)
  +2 : дисциплина подгруппа-2 (если делится)
  +4 : аудитория подгруппа-1
  +5 : аудитория подгруппа-2

Аналогично для преподавателей:
  +0 : преподаватель подгруппа-1
  +2 : преподаватель подгруппа-2
"""
import re
from datetime import datetime
from typing import Optional

import openpyxl

BLOCK_STARTS = [1, 7, 13, 19]   # начало каждого блока группы (0-индекс)
GROUP_RE = re.compile(r"^[0-9А-ЯA-Zа-яa-z].*[-–]")

PAIR_TIMES = {
    1: "08:00–09:30",
    2: "09:40–11:10",
    3: "11:30–13:00",
    4: "13:20–14:50",
    5: "15:00–16:30",
    6: "16:40–18:10",
    7: "18:20–19:50",
    8: "20:00–21:30",
}


def _cell(row: tuple, idx: int) -> str:
    if idx >= len(row):
        return ""
    v = row[idx]
    if v is None:
        return ""
    return str(v).strip()


def _is_group_row(row: tuple) -> list[Optional[str]]:
    """Если строка содержит имена групп в блочных позициях — вернуть список."""
    found = []
    has_any = False
    for col in BLOCK_STARTS:
        v = _cell(row, col)
        if v and GROUP_RE.match(v):
            found.append(v)
            has_any = True
        else:
            found.append(None)
    return found if has_any else []


def _normalize_room(raw: str) -> str:
    if not raw or raw in ("None", "null"):
        return ""
    raw = raw.strip()
    if raw.lower() in ("maх", "max", "мах", "макс", "макс."):
        return "Макс."
    if raw.lower() in ("сам.изуч", "сам. изуч.", "самост"):
        return "Сам.изуч."
    return raw


def parse_xlsx(file_path_or_bytes) -> dict:
    """
    Возвращает словарь:
    {
        "date": "10.03.2026",
        "day_of_week": "Вторник",
        "lessons": [
            {
                "date": date,
                "day_of_week": str,
                "pair_number": int,
                "subgroup": int | None,
                "group": str,
                "teacher": str,
                "subject": str,
                "room": str,
            },
            ...
        ]
    }
    """
    if isinstance(file_path_or_bytes, (str, bytes)):
        wb = openpyxl.load_workbook(file_path_or_bytes, read_only=True, data_only=True)
    else:
        # Django InMemoryUploadedFile / file-like
        wb = openpyxl.load_workbook(file_path_or_bytes, read_only=True, data_only=True)

    sheet_name = wb.sheetnames[0]
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    day_of_week = sheet_name.strip()

    # Дата из первой ячейки
    title = _cell(rows[0], 0) if rows else ""
    date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title)
    if date_match:
        parsed_date = datetime.strptime(date_match.group(0), "%d.%m.%Y").date()
        date_str = date_match.group(0)
    else:
        from datetime import date as d_today
        parsed_date = d_today.today()
        date_str = parsed_date.strftime("%d.%m.%Y")

    lessons = []
    current_groups: list[Optional[str]] = [None, None, None, None]

    i = 0
    while i < len(rows):
        row = rows[i]

        # Пустая строка
        if all(v is None for v in row):
            i += 1
            continue

        # Проверяем строку с именами групп
        group_row = _is_group_row(row)
        if group_row:
            current_groups = group_row
            i += 1
            continue

        # Проверяем строку с номером пары
        pair_num_raw = row[0] if row else None
        if pair_num_raw is not None and str(pair_num_raw).strip().isdigit():
            pair_num = int(str(pair_num_raw).strip())
            if 1 <= pair_num <= 8:
                # Следующая строка — преподаватели (если не новая пара и не группы)
                teacher_row = None
                if i + 1 < len(rows):
                    next_row = rows[i + 1]
                    nv0 = next_row[0] if next_row else None
                    # Следующая строка — не пара и не группы
                    if (nv0 is None or not str(nv0).strip().isdigit()) and not _is_group_row(next_row):
                        teacher_row = next_row

                for block_idx, col in enumerate(BLOCK_STARTS):
                    group_name = current_groups[block_idx] if block_idx < len(current_groups) else None
                    if not group_name:
                        continue

                    subj1  = _cell(row, col + 0) or _cell(row, col + 1)
                    subj2  = _cell(row, col + 2) or _cell(row, col + 3)
                    room1  = _normalize_room(_cell(row, col + 4))
                    room2  = _normalize_room(_cell(row, col + 5))

                    teach1 = ""
                    teach2 = ""
                    if teacher_row is not None:
                        teach1 = _cell(teacher_row, col + 0) or _cell(teacher_row, col + 1)
                        teach2 = _cell(teacher_row, col + 2) or _cell(teacher_row, col + 3)

                    if subj1 and subj2:
                        # Две подгруппы
                        lessons.append(_make(parsed_date, day_of_week, pair_num, 1,
                                             group_name, teach1, subj1, room1))
                        lessons.append(_make(parsed_date, day_of_week, pair_num, 2,
                                             group_name, teach2, subj2, room2))
                    elif subj1:
                        lessons.append(_make(parsed_date, day_of_week, pair_num, None,
                                             group_name, teach1, subj1, room1 or room2))

                i += 2 if teacher_row is not None else 1
                continue

        i += 1

    return {
        "date": date_str,
        "day_of_week": day_of_week,
        "lessons": lessons,
    }


def _make(date, dow, pair, subgroup, group, teacher, subject, room) -> dict:
    return {
        "date":        date,
        "day_of_week": dow,
        "pair_number": pair,
        "subgroup":    subgroup,
        "group":       group,
        "teacher":     teacher.strip() if teacher else "",
        "subject":     subject.strip(),
        "room":        room,
    }
