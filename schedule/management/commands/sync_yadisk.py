import logging
import os
import re
from datetime import datetime
from io import BytesIO

import requests
from django.core.cache import cache
from django.core.management.base import BaseCommand

from schedule.models import Group, Lesson, Subject, Teacher
from schedule.parser import parse_xlsx

logger = logging.getLogger(__name__)

PUBLIC_KEY = "https://disk.360.yandex.ru/d/g3_4Rr1v5k-WDQ"
API_BASE   = "https://cloud-api.yandex.net/v1/disk/public/resources"
SITE_URL   = "https://kemgtt.serverkiwi.ru"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _extract_date(filename):
    m = DATE_RE.search(filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def _get_file_list():
    resp = requests.get(API_BASE, params={"public_key": PUBLIC_KEY, "limit": 100}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("_embedded", {}).get("items", [])


def _download_file(filename):
    dl = requests.get(f"{API_BASE}/download",
                      params={"public_key": PUBLIC_KEY, "path": f"/{filename}"}, timeout=15)
    dl.raise_for_status()
    f = requests.get(dl.json()["href"], timeout=30)
    f.raise_for_status()
    return f.content


def _save_lessons(lessons):
    created = 0
    for lesson in lessons:
        group,   _ = Group.objects.get_or_create(name=lesson["group"])
        teacher, _ = Teacher.objects.get_or_create(
            name=" ".join(lesson["teacher"].split()) if lesson["teacher"] else "Ne ukazan"
        )
        subject, _ = Subject.objects.get_or_create(name=lesson["subject"])
        _, is_new = Lesson.objects.get_or_create(
            date=lesson["date"],
            pair_number=lesson["pair_number"],
            subgroup=lesson["subgroup"],
            group=group,
            defaults={
                "day_of_week": lesson["day_of_week"],
                "teacher":     teacher,
                "subject":     subject,
                "room":        lesson["room"],
            },
        )
        if is_new:
            created += 1
    return created


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
        lines = ["<b>Novoe raspisanie zagruzheno</b>\n"]
        for gname, (fdate, cnt) in by_group.items():
            lines.append(f"{gname} -- {fdate.strftime('%d.%m.%Y')} ({cnt} zanyatiy)")
        lines.append(f"\n{SITE_URL}")
        _send_tg(token, admin_chat_id, "\n".join(lines))

    subs = Subscription.objects.filter(
        group__name__in=list(by_group.keys())
    ).select_related("group")

    chat_groups = {}
    for sub in subs:
        chat_groups.setdefault(sub.chat_id, []).append(sub.group.name)

    logger.info("Rassylka: %d podpischikov", len(chat_groups))

    for chat_id, groups in chat_groups.items():
        lines = ["<b>Poyavilos novoe raspisanie!</b>\n"]
        for gname in groups:
            fdate, cnt = by_group[gname]
            lines.append(f"<b>{gname}</b> -- {fdate.strftime('%d.%m.%Y')}")
        lines.append(f"\n<a href='{SITE_URL}'>Otkryt raspisanie</a>")
        _send_tg(token, chat_id, "\n".join(lines))


class Command(BaseCommand):
    help = "Skachat novye fayly raspisaniya s Yandex.Diska"

    def handle(self, *args, **kwargs):
        self.stdout.write("=== sync_yadisk ===")
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")

        try:
            items = _get_file_list()
        except Exception as e:
            self.stderr.write(f"[OSHIBKA] {e}")
            return

        xlsx_files = [
            item for item in items
            if item.get("name", "").startswith("studentam_")
            and item.get("name", "").endswith(".xlsx")
        ]

        if not xlsx_files:
            self.stdout.write("Faylov ne naydeno.")
            return

        self.stdout.write(f"Naydeno faylov: {len(xlsx_files)}")
        imported = []

        for item in xlsx_files:
            name = item["name"]
            file_date = _extract_date(name)

            if not file_date:
                self.stdout.write(f"  {name} -- ne udalos izvlech datu, propuskayu")
                continue

            if Lesson.objects.filter(date=file_date).exists():
                self.stdout.write(f"  {name} -- uzhe v baze ({file_date}), propuskayu")
                continue

            try:
                content = _download_file(name)
                self.stdout.write(f"  {name} -- skachan ({len(content)//1024} KB)")
            except Exception as e:
                self.stderr.write(f"  {name} -- [OSHIBKA skachivaniay] {e}")
                continue

            try:
                data    = parse_xlsx(BytesIO(content))
                lessons = data["lessons"]
                self.stdout.write(f"  {name} -- {len(lessons)} zanyatiy")
            except Exception as e:
                self.stderr.write(f"  {name} -- [OSHIBKA parsinga] {e}")
                continue

            try:
                created = _save_lessons(lessons)
                self.stdout.write(f"  {name} -- sokhraneno {created} novykh")
                groups_in_file = set(l["group"] for l in lessons)
                for gname in groups_in_file:
                    cnt = sum(1 for l in lessons if l["group"] == gname)
                    imported.append((gname, file_date, cnt))
            except Exception as e:
                self.stderr.write(f"  {name} -- [OSHIBKA sokhraneniya] {e}")
                continue

        if imported:
            cache.clear()  # сбросить кэш страниц сайта
            _notify_subscribers(token, imported)
            self.stdout.write("Uvedomleniya otpravleny.")

        total = sum(c for _, _, c in imported)
        self.stdout.write(f"=== Gotovo. Dobavleno: {total} ===")
