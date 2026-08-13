import logging
import re
import time
from datetime import datetime
from io import BytesIO

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from schedule.parser import parse_xlsx
from schedule.services import save_lessons

logger = logging.getLogger(__name__)

API_BASE = "https://cloud-api.yandex.net/v1/disk/public/resources"
SITE_URL = "https://kemgtt.serverkiwi.ru"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(filename):
    m = DATE_RE.search(filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _get_file_list(public_key):
    resp = requests.get(API_BASE, params={"public_key": public_key, "limit": 100}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("_embedded", {}).get("items", [])


def _download_file(public_key, filename):
    dl = requests.get(f"{API_BASE}/download",
                      params={"public_key": public_key, "path": f"/{filename}"}, timeout=15)
    dl.raise_for_status()
    f = requests.get(dl.json()["href"], timeout=30)
    f.raise_for_status()
    return f.content


def _send_tg(token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Не удалось отправить сообщение chat=%s: %s", chat_id, e)


def _notify_subscribers(token, imported_files):
    if not token or not imported_files:
        return

    from schedule.models import Subscription

    by_group = {}
    for group_name, fdate, cnt in imported_files:
        by_group[group_name] = (fdate, cnt)

    if not by_group:
        return

    admin_chat_id = getattr(settings, "ADMIN_CHAT_ID", "") or ""
    if admin_chat_id:
        lines = ["<b>Загружено новое расписание</b>\n"]
        for gname, (fdate, cnt) in by_group.items():
            lines.append(f"{gname} — {fdate.strftime('%d.%m.%Y')} ({cnt} занятий)")
        lines.append(f"\n{SITE_URL}")
        _send_tg(token, admin_chat_id, "\n".join(lines))

    subs = Subscription.objects.filter(
        group__name__in=list(by_group.keys())
    ).select_related("group")

    chat_groups = {}
    for sub in subs:
        chat_groups.setdefault(sub.chat_id, []).append(sub.group.name)

    logger.info("Рассылка уведомлений: %d подписчиков", len(chat_groups))

    for chat_id, groups in chat_groups.items():
        lines = ["<b>Появилось новое расписание!</b>\n"]
        for gname in groups:
            fdate, _cnt = by_group[gname]
            lines.append(f"<b>{gname}</b> — {fdate.strftime('%d.%m.%Y')}")
        lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
        _send_tg(token, chat_id, "\n".join(lines))


def sync_once(stdout, stderr):
    from schedule.models import Lesson

    public_key = getattr(settings, "YADISK_PUBLIC_KEY", "") or ""
    if not public_key:
        stderr.write("Не задан YADISK_PUBLIC_KEY в .env!")
        return

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""

    try:
        items = _get_file_list(public_key)
    except Exception as e:
        stderr.write(f"[ОШИБКА] Не удалось получить список файлов: {e}")
        return

    xlsx_files = [
        item for item in items
        if item.get("name", "").startswith("studentam_")
        and item.get("name", "").endswith(".xlsx")
    ]

    if not xlsx_files:
        stdout.write("Файлов не найдено.")
        return

    stdout.write(f"Найдено файлов: {len(xlsx_files)}")
    imported = []

    for item in xlsx_files:
        name = item["name"]
        file_date = _extract_date(name)

        if not file_date:
            stdout.write(f"  {name} — не удалось извлечь дату, пропускаю")
            continue

        if Lesson.objects.filter(date=file_date).exists():
            stdout.write(f"  {name} — уже в базе ({file_date}), пропускаю")
            continue

        try:
            content = _download_file(public_key, name)
            stdout.write(f"  {name} — скачан ({len(content)//1024} КБ)")
        except Exception as e:
            stderr.write(f"  {name} — [ОШИБКА скачивания] {e}")
            continue

        try:
            data    = parse_xlsx(BytesIO(content))
            lessons = data["lessons"]
            stdout.write(f"  {name} — {len(lessons)} занятий")
        except Exception as e:
            stderr.write(f"  {name} — [ОШИБКА парсинга] {e}")
            continue

        try:
            processed, created = save_lessons(lessons, update_existing=False)
            stdout.write(f"  {name} — сохранено {processed}, новых {created}")
            groups_in_file = set(l["group"] for l in lessons)
            for gname in groups_in_file:
                cnt = sum(1 for l in lessons if l["group"] == gname)
                imported.append((gname, file_date, cnt))
        except Exception as e:
            stderr.write(f"  {name} — [ОШИБКА сохранения] {e}")
            continue

    if imported:
        _notify_subscribers(token, imported)
        stdout.write("Уведомления отправлены.")

    total = sum(c for _, _, c in imported)
    stdout.write(f"=== Готово. Добавлено: {total} ===")


class Command(BaseCommand):
    help = "Скачать новые файлы расписания с Яндекс.Диска"

    def add_arguments(self, parser):
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Запускать синхронизацию в цикле с заданным интервалом",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            help="Интервал синхронизации в секундах (по умолчанию — SCHEDULE_SYNC_INTERVAL из .env, 900 с)",
        )

    def handle(self, *args, **kwargs):
        interval = kwargs.get("interval") or getattr(settings, "SCHEDULE_SYNC_INTERVAL", 900)
        watch = kwargs.get("watch")

        if not watch:
            sync_once(self.stdout, self.stderr)
            return

        self.stdout.write(f"Запуск синхронизации в цикле, интервал {interval} с")
        while True:
            try:
                sync_once(self.stdout, self.stderr)
            except Exception as e:
                self.stderr.write(f"[ОШИБКА] {e}")
            self.stdout.write(f"Следующая проверка через {interval} с…")
            time.sleep(interval)
