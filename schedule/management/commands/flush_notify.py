"""Доставка уведомлений из Redis-очереди yadisk:notify в Telegram.

Запускается в sync-контейнере: bridge-сеть (видит db/redis), TG-трафик — через
socks-прокси на host.docker.internal:1080 (aiohttp-socks уже в requirements).

Куда доставляем:
- ChatBinding (чат привязан к одной группе): только события ЭТОЙ группы,
  в заданный топик (message_thread_id), если он указан;
- Subscription (обычные подписки): как раньше — все события по подписанным
  группам (привязанные чаты из обычной доставки исключены, чтобы не дублить);
- ADMIN_CHAT_ID: все события (страховка), если этот чат не охвачен выше.
"""
import asyncio
import json
import logging
import os

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

SITE_URL = "https://kemgtt.serverkiwi.ru"


async def _deliver_all(token, targets):
    """targets: [(chat_id, thread_id|None, text, png|None), ...].

    png is not None -> sendPhoto с caption (карточка расписания),
    иначе sendMessage. Возвращает set неудачных chat_id."""
    import aiohttp
    from aiohttp_socks import ProxyConnector
    proxy = os.getenv("PROXY_URL", "")
    connector = ProxyConnector.from_url(proxy) if proxy else None
    failed = set()
    async with aiohttp.ClientSession(connector=connector) as session:
        for chat_id, thread_id, text, png in targets:
            if thread_id:
                pass
            try:
                if png:
                    import io
                    photo = io.BytesIO(png)
                    photo.name = "schedule.png"
                    form = aiohttp.FormData()
                    form.add_field("chat_id", str(chat_id))
                    form.add_field("caption", text[:1024])
                    form.add_field("parse_mode", "HTML")
                    form.add_field("photo", photo, filename="schedule.png",
                                   content_type="image/png")
                    if thread_id:
                        form.add_field("message_thread_id", str(thread_id))
                    url = f"https://api.telegram.org/bot{token}/sendPhoto"
                else:
                    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
                    if thread_id:
                        body["message_thread_id"] = thread_id
                    form = None
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                kwargs = {"data": form} if form else {"json": body}
                async with session.post(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    **kwargs,
                ) as resp:
                    if resp.status != 200:
                        logger.warning("TG %s (topic=%s) -> %s: %s",
                                       chat_id, thread_id, resp.status,
                                       (await resp.text())[:120])
                        failed.add(chat_id)
            except Exception as e:
                logger.warning("TG send error chat=%s: %s", chat_id, e)
                failed.add(chat_id)
    return failed


def _deliver(token, targets):
    return asyncio.run(_deliver_all(token, targets))


def _fetch_day_card(group_name: str, d: str) -> bytes | None:
    """Карточка расписания группы на дату (для фото-уведомления)."""
    try:
        from schedule.models import Lesson
        from tgbot.schedule_card import render_schedule_card
        lessons = list(Lesson.objects.filter(group__name=group_name, date=d)
                       .select_related("teacher", "subject")
                       .order_by("pair_number", "subgroup"))
        rows = [{"pair": l.pair_number,
                 "time": _pair_time(l.pair_number),
                 "subject": l.subject.name,
                 "room": l.room,
                 "subgroup": l.subgroup,
                 "teacher": l.teacher.name} for l in lessons]
        return render_schedule_card(f"Группа {group_name}", _fmt_date(d), rows, "teacher")
    except Exception as e:
        logger.error("fetch_day_card(%s, %s): %s", group_name, d, e)
        return None


PAIR_TIMES = {
    1: "08:30–10:00", 2: "10:20–11:50", 3: "12:10–13:40",
    4: "14:00–15:30", 5: "15:40–17:10", 6: "17:15–18:45",
    7: "19:00–20:30", 8: "20:00–21:30",
}


def _pair_time(n):
    return PAIR_TIMES.get(n, "")


def _fmt_date(d: str) -> str:
    from datetime import date as _d
    WD = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    MO = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
    try:
        dt = _d.fromisoformat(d)
        return f"{WD[dt.weekday()]}, {dt.day} {MO[dt.month - 1]} {dt.year}"
    except Exception:
        return d


def _names(payload):
    if payload.get("type") == "new":
        return list(dict.fromkeys(g for g, _d, _c in payload["imported"]))
    return list(dict.fromkeys(
        g for pairs in payload["changes"].values() for g, _ in pairs))


def _render(payload, only_group=None):
    """Текст события; only_group — оставить в тексте только эти группы
    (строка, множество групп или None = все)."""
    from html import escape
    if isinstance(only_group, str):
        only_group = {only_group}
    if payload.get("type") == "new":
        imported = [(g, d) for g, d, _c in payload["imported"]
                    if only_group is None or g in only_group]
        if not imported:
            return ""
        lines = ["<b>Появилось новое расписание!</b>\n"]
        for g, d in imported:
            y, m, dd = d.split("-")
            lines.append(f"<b>{escape(g)}</b> — {dd}.{m}.{y}")
        lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
        return "\n".join(lines)
    lines = []
    for d, pairs in sorted(payload.get("changes", {}).items()):
        y, m, dd = d.split("-")
        ds = f"{dd}.{m}.{y}"
        for g, gl in pairs:
            if only_group is not None and g not in only_group:
                continue
            lines.append(f"<b>⚠️ Расписание на {ds} изменилось</b>")
            lines.append(f"<b>{escape(g)}</b>")
            lines.extend("• " + escape(x) for x in gl[:8])
            if len(gl) > 8:
                lines.append(f"… и ещё {len(gl) - 8} изм.")
    if not lines:
        return ""
    lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Доставить накопленные уведомления из Redis в Telegram"

    def handle(self, *args, **kwargs):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            self.stderr.write("TELEGRAM_BOT_TOKEN не задан")
            return
        from django_redis import get_redis_connection
        client = get_redis_connection("default")
        delivered = 0
        while True:
            item = client.lpop("yadisk:notify")
            if item is None:
                break
            try:
                payload = json.loads(item)
            except Exception:
                logger.warning("bad queue item: %r", item[:100])
                continue

            # Повтор после неудачи: досылаем только тем, кому не ушло (текстом,
            # карточку уже пытались отправить фото)
            retry = payload.pop("retry_targets", None)
            if retry is not None:
                targets = [(*t, None) for t in retry]
            else:
                from schedule.models import ChatBinding, ChatTopicBinding, Subscription
                names = _names(payload)

                # Даты события (для карточек): новые — все imported-даты,
                # изменения — ключи changes
                if payload.get("type") == "new":
                    event_dates = list(dict.fromkeys(d for _g, d, _c in payload["imported"]))
                else:
                    event_dates = list(payload.get("changes", {}).keys())

                # 1) Топик-биндинги: топик → своя группа (форум-чаты)
                #    Отправляем КАРТИНКУ расписания своей группы на дату события
                topic_bindings = list(ChatTopicBinding.objects.filter(
                    group__name__in=names).select_related("group"))
                topic_target_keys = {(t.chat_id, t.thread_id) for t in topic_bindings}
                targets = []
                for t in topic_bindings:
                    text_t = _render(payload, only_group=t.group.name)
                    if not text_t:
                        continue
                    d = event_dates[0] if event_dates else None
                    png = _fetch_day_card(t.group.name, d) if d else None
                    targets.append((t.chat_id, t.thread_id, text_t, png))

                # 2) Привязка всего чата (не-форумы / General) — без дублей с топиками
                bindings = list(ChatBinding.objects.filter(
                    group__name__in=names).select_related("group"))
                bound_ids = {b.chat_id for b in bindings}
                for b in bindings:
                    if (b.chat_id, b.thread_id) in topic_target_keys:
                        continue  # этот чат уже обслужен топик-биндингами
                    text_b = _render(payload, only_group=b.group.name)
                    if not text_b:
                        continue
                    d = event_dates[0] if event_dates else None
                    png = _fetch_day_card(b.group.name, d) if d else None
                    targets.append((b.chat_id, b.thread_id, text_b, png))

                # 3) Подписки: каждый подписчик получает ТОЛЬКО свои группы
                #    (карточка первой своей затронутой группы на дату события),
                #    в топик, где оформил подписку (форум), иначе общий поток
                text_all = _render(payload)  # для админа-страховки
                sub_chats = set()
                for s in (Subscription.objects.filter(group__name__in=names)
                          .exclude(chat_id__in=bound_ids)
                          .select_related("group")):
                    my_names = sorted(set(Subscription.objects.filter(
                        chat_id=s.chat_id, group__name__in=names
                    ).values_list("group__name", flat=True)))
                    text_s = _render(payload, only_group=set(my_names))
                    if not text_s:
                        continue
                    key = (s.chat_id, s.thread_id)
                    if key in topic_target_keys:
                        continue
                    d = event_dates[0] if event_dates else None
                    png = _fetch_day_card(my_names[0], d) if d else None
                    targets.append((s.chat_id, s.thread_id, text_s, png))
                    sub_chats.discard(s.chat_id)
                    sub_chats.add(s.chat_id)

                admin_chat_id = os.getenv("ADMIN_CHAT_ID")
                if admin_chat_id:
                    try:
                        admin_id = int(admin_chat_id)
                    except ValueError:
                        admin_id = None
                    if (admin_id and admin_id not in bound_ids
                            and admin_id not in sub_chats and text_all):
                        # админ-страховка — ВСЕГДА текстом (надёжный фоллбек,
                        # текст читается при любом сбое рендера/сети)
                        targets.append((admin_id, None, text_all, None))

            if not targets:
                delivered += 1
                continue
            failed = _deliver(token, targets)
            if not failed:
                delivered += 1
                continue
            # неудача: вернуть в конец очереди только неотявленные адресаты;
            # после 5 попыток выбрасываем, чтобы не клинить очередь
            payload["attempts"] = payload.get("attempts", 0) + 1
            if payload["attempts"] >= 5:
                logger.error("drop notify after %s attempts", payload["attempts"])
                delivered += 1
            else:
                payload["retry_targets"] = [(c, t, x) for (c, t, x, _p) in targets if c in failed]
                client.rpush("yadisk:notify",
                             json.dumps(payload, ensure_ascii=False))
                break
        self.stdout.write(f"доставлено событий: {delivered}")
