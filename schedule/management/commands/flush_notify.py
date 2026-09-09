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
    """targets: [(chat_id, thread_id|None, text), ...]. Возвращает set неудачных chat_id."""
    import aiohttp
    from aiohttp_socks import ProxyConnector
    proxy = os.getenv("PROXY_URL", "")
    connector = ProxyConnector.from_url(proxy) if proxy else None
    failed = set()
    async with aiohttp.ClientSession(connector=connector) as session:
        for chat_id, thread_id, text in targets:
            body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            if thread_id:
                body["message_thread_id"] = thread_id
            try:
                async with session.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=15),
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


def _names(payload):
    if payload.get("type") == "new":
        return list(dict.fromkeys(g for g, _d, _c in payload["imported"]))
    return list(dict.fromkeys(
        g for pairs in payload["changes"].values() for g, _ in pairs))


def _render(payload, only_group=None):
    """Текст события; only_group — оставить в тексте только эту группу."""
    from html import escape
    if payload.get("type") == "new":
        imported = [(g, d) for g, d, _c in payload["imported"]
                    if only_group is None or g == only_group]
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
            if only_group is not None and g != only_group:
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

            # Повтор после неудачи: досылаем только тем, кому не ушло
            retry = payload.pop("retry_targets", None)
            if retry is not None:
                targets = [(t[0], t[1], t[2]) for t in retry]
            else:
                from schedule.models import ChatBinding, Subscription
                names = _names(payload)

                bindings = list(ChatBinding.objects.filter(
                    group__name__in=names).select_related("group"))
                bound_ids = {b.chat_id for b in bindings}
                targets = []
                for b in bindings:
                    text_b = _render(payload, only_group=b.group.name)
                    if text_b:
                        targets.append((b.chat_id, b.thread_id, text_b))

                sub_chats = set(Subscription.objects.filter(
                    group__name__in=names
                ).exclude(chat_id__in=bound_ids).values_list("chat_id", flat=True))
                text_all = _render(payload)
                for c in sub_chats:
                    targets.append((c, None, text_all))

                admin_chat_id = os.getenv("ADMIN_CHAT_ID")
                if admin_chat_id:
                    try:
                        admin_id = int(admin_chat_id)
                    except ValueError:
                        admin_id = None
                    if (admin_id and admin_id not in bound_ids
                            and admin_id not in sub_chats and text_all):
                        targets.append((admin_id, None, text_all))

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
                payload["retry_targets"] = [(c, t, x) for (c, t, x) in targets if c in failed]
                client.rpush("yadisk:notify",
                             json.dumps(payload, ensure_ascii=False))
                break
        self.stdout.write(f"доставлено событий: {delivered}")
