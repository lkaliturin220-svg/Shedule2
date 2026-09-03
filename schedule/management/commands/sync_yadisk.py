import logging
import os
import re
from datetime import datetime
from html import escape
from io import BytesIO

import requests
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from schedule.models import Group, Lesson, Subject, Teacher
from schedule.parser import parse_xlsx

logger = logging.getLogger(__name__)

PUBLIC_KEY = "https://disk.360.yandex.ru/d/g3_4Rr1v5k-WDQ"
API_BASE   = "https://cloud-api.yandex.net/v1/disk/public/resources"
SITE_URL   = "https://kemgtt.serverkiwi.ru"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(filename):
    m = DATE_RE.search(filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _get_file_list():
    resp = requests.get(API_BASE, params={"public_key": PUBLIC_KEY, "limit": 100}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("_embedded", {}).get("items", [])


def _download_file(filename):
    # Yandex API requires an absolute path (leading "/") for public resources;
    # a bare filename returns 404 DiskNotFoundError (observed 2026-09-03).
    dl = requests.get(f"{API_BASE}/download",
                      params={"public_key": PUBLIC_KEY,
                              "path": "/" + filename.lstrip("/")}, timeout=15)
    dl.raise_for_status()
    f = requests.get(dl.json()["href"], timeout=30)
    f.raise_for_status()
    return f.content


def _fmt(key, data):
    """Строка описания занятия: группа · N-я пара пгX: предмет, каб. Y (преподаватель)."""
    group, pair, sub = key
    subject, teacher, room = data
    sub_s = f" пг{sub}" if sub else ""
    return f"{pair}-я пара{sub_s}: {subject}, каб. {room or '—'} ({teacher})"


def _replace_date_lessons(file_date, lessons):
    """Полностью заменяет занятия даты данными из файла (файл — источник истины).

    Возвращает (existed, count, diff), где diff — отсортированный список
    (group_name, [строки изменений]) по группам с изменениями.
    """
    old_rows = {
        (l.group.name, l.pair_number, l.subgroup): (l.subject.name, l.teacher.name, l.room)
        for l in Lesson.objects.filter(date=file_date).select_related("group", "subject", "teacher")
    }

    new_rows = {}
    objs = []
    for row in lessons:
        if not row["subject"] or not row["group"]:
            continue
        group = Group.get_or_create_by_name(row["group"])
        teacher, _ = Teacher.objects.get_or_create(
            name=" ".join(row["teacher"].split()) if row["teacher"] else "Не указан"
        )
        subject, _ = Subject.objects.get_or_create(name=row["subject"])
        key = (group.name, row["pair_number"], row["subgroup"])
        new_rows[key] = (subject.name, teacher.name, row["room"])
        objs.append(Lesson(
            date=file_date, day_of_week=row["day_of_week"],
            pair_number=row["pair_number"], subgroup=row["subgroup"],
            group=group, teacher=teacher, subject=subject, room=row["room"],
        ))

    with transaction.atomic():
        Lesson.objects.filter(date=file_date).delete()
        Lesson.objects.bulk_create(objs)

    lines_by_group = {}
    for key in sorted(new_rows):
        if key not in old_rows:
            lines_by_group.setdefault(key[0], []).append("+ " + _fmt(key, new_rows[key]))
    for key in sorted(old_rows):
        if key not in new_rows:
            lines_by_group.setdefault(key[0], []).append("− " + _fmt(key, old_rows[key]))
    for key in sorted(new_rows):
        if key in old_rows and new_rows[key] != old_rows[key]:
            lines_by_group.setdefault(key[0], []).append("~ " + _fmt(key, new_rows[key]))

    existed = bool(old_rows)
    return existed, len(objs), sorted(lines_by_group.items())


def _send_tg(token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram send error chat=%s: %s", chat_id, e)


def _notify_subscribers(token, imported_files):
    """Рассылка «появилось новое расписание» по группам из новых дат."""
    if not token or not imported_files:
        return
    try:
        from schedule.models import Subscription
    except ImportError:
        logger.error("Subscription model not found")
        return

    by_group = {}
    for group_name, fdate, count in imported_files:
        by_group[group_name] = (fdate, count)
    if not by_group:
        return

    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if admin_chat_id:
        lines = ["<b>Новое расписание загружено</b>\n"]
        for gname, (fdate, cnt) in by_group.items():
            lines.append(f"{escape(gname)} — {fdate.strftime('%d.%m.%Y')} ({cnt} занятий)")
        lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
        _send_tg(token, admin_chat_id, "\n".join(lines))

    subs = Subscription.objects.filter(
        group__name__in=list(by_group.keys())
    ).select_related("group")

    chat_groups = {}
    for sub in subs:
        chat_groups.setdefault(sub.chat_id, []).append(sub.group.name)

    logger.info("Рассылка (новые даты): %d подписчиков", len(chat_groups))

    for chat_id, groups in chat_groups.items():
        lines = ["<b>Появилось новое расписание!</b>\n"]
        for gname in groups:
            fdate, _cnt = by_group[gname]
            lines.append(f"<b>{escape(gname)}</b> — {fdate.strftime('%d.%m.%Y')}")
        lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
        _send_tg(token, chat_id, "\n".join(lines))


def _notify_changes(token, changes_by_date):
    """Рассылка об изменениях существующего расписания.

    changes_by_date: {date: [(group_name, [строки изменений])]}
    """
    if not token or not changes_by_date:
        return
    try:
        from schedule.models import Subscription
    except ImportError:
        logger.error("Subscription model not found")
        return

    affected = sorted({g for pairs in changes_by_date.values() for g, _ in pairs})
    subs = Subscription.objects.filter(group__name__in=affected).select_related("group")
    chat_groups = {}
    for sub in subs:
        chat_groups.setdefault(sub.chat_id, set()).add(sub.group.name)

    logger.info("Рассылка (изменения): %d подписчиков", len(chat_groups))

    for date, pairs in sorted(changes_by_date.items()):
        ds = date.strftime("%d.%m.%Y")
        for chat_id, groups in chat_groups.items():
            lines = [f"<b>⚠️ Расписание на {ds} изменилось</b>"]
            sent = 0
            for gname, glines in sorted(pairs):
                if gname not in groups:
                    continue
                lines.append(f"\n<b>{escape(gname)}</b>")
                lines.extend("• " + escape(l) for l in glines[:8])
                if len(glines) > 8:
                    lines.append(f"… и ещё {len(glines) - 8} изм.")
                sent += len(glines)
            if not sent:
                continue
            lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
            _send_tg(token, chat_id, "\n".join(lines))

    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if admin_chat_id:
        total = sum(len(gl) for pairs in changes_by_date.values() for _, gl in pairs)
        ds_list = ", ".join(d.strftime("%d.%m") for d in sorted(changes_by_date))
        _send_tg(token, admin_chat_id,
                 f"<b>Обновление расписания</b> — {total} изм. ({ds_list})\n{SITE_URL}")


class Command(BaseCommand):
    help = "Синхронизация расписания с Яндекс.Диском: новые даты и изменения"

    def handle(self, *args, **kwargs):
        self.stdout.write("=== sync_yadisk ===")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")

        try:
            items = _get_file_list()
        except Exception as e:
            self.stderr.write(f"[ОШИБКА] {e}")
            return

        xlsx_files = [
            item for item in items
            if item.get("name", "").startswith("studentam_")
            and item.get("name", "").endswith(".xlsx")
        ]

        if not xlsx_files:
            self.stdout.write("Файлов не найдено.")
            return

        self.stdout.write(f"Найдено файлов: {len(xlsx_files)}")
        imported = []          # (group, date, count) — новые даты
        changes_by_date = {}   # {date: [(group, [diff-строки])]} — изменения

        for item in xlsx_files:
            name = item["name"]
            file_date = _extract_date(name)

            if not file_date:
                self.stdout.write(f"  {name} — не удалось извлечь дату, пропускаю")
                continue

            try:
                content = _download_file(name)
                self.stdout.write(f"  {name} — скачан ({len(content)//1024} KB)")
            except Exception as e:
                self.stderr.write(f"  {name} — [ОШИБКА скачивания] {e}")
                continue

            try:
                data = parse_xlsx(BytesIO(content))
                lessons = data["lessons"]
            except Exception as e:
                self.stderr.write(f"  {name} — [ОШИБКА парсинга] {e}")
                continue

            try:
                existed, count, diff = _replace_date_lessons(file_date, lessons)
            except Exception as e:
                self.stderr.write(f"  {name} — [ОШИБКА сохранения] {e}")
                continue

            if not existed:
                self.stdout.write(f"  {name} — новая дата {file_date}: {count} занятий")
                groups_in_file = set(l["group"] for l in lessons if l["group"])
                for gname in groups_in_file:
                    cnt = sum(1 for l in lessons if l["group"] == gname)
                    imported.append((gname, file_date, cnt))
            elif diff:
                n_changes = sum(len(gl) for _, gl in diff)
                self.stdout.write(f"  {name} — изменения на {file_date}: {n_changes}")
                changes_by_date[file_date] = diff
            else:
                self.stdout.write(f"  {name} — без изменений ({file_date})")

        if imported:
            cache.clear()  # сбросить кэш страниц сайта
            _notify_subscribers(token, imported)
            self.stdout.write("Уведомления о новых датах отправлены.")

        if changes_by_date:
            cache.clear()
            _notify_changes(token, changes_by_date)
            self.stdout.write("Уведомления об изменениях отправлены.")

        total = sum(c for _, _, c in imported)
        self.stdout.write(f"=== Готово. Новых занятий: {total} ===")
