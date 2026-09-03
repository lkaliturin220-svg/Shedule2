"""Доставка уведомлений из Redis-очереди yadisk:notify в Telegram.

Запускается в sync-контейнере: bridge-сеть (видит db/redis), TG-трафик — через
socks-прокси на host.docker.internal:1080 (aiohttp-socks уже в requirements).
"""
import asyncio
import json
import logging
import os

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

SITE_URL = "https://kemgtt.serverkiwi.ru"


async def _deliver_all(token, chats, text):
    import aiohttp
    from aiohttp_socks import ProxyConnector
    proxy = os.getenv("PROXY_URL", "")
    connector = ProxyConnector.from_url(proxy) if proxy else None
    failed = set()
    async with aiohttp.ClientSession(connector=connector) as session:
        for chat_id in chats:
            try:
                async with session.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("TG %s -> %s: %s",
                                       chat_id, resp.status,
                                       (await resp.text())[:120])
                        failed.add(chat_id)
            except Exception as e:
                logger.warning("TG send error chat=%s: %s", chat_id, e)
                failed.add(chat_id)
    return failed


def _deliver(token, chats, text):
    return asyncio.run(_deliver_all(token, chats, text))


def _render(payload):
    from html import escape
    if payload.get("type") == "new":
        lines = ["<b>Появилось новое расписание!</b>\n"]
        for g, d, _c in payload["imported"]:
            y, m, dd = d.split("-")
            lines.append(f"<b>{escape(g)}</b> — {dd}.{m}.{y}")
        lines.append(f"\n<a href='{SITE_URL}'>Открыть расписание</a>")
        return "\n".join(lines)
    lines = []
    for d, pairs in sorted(payload.get("changes", {}).items()):
        y, m, dd = d.split("-")
        ds = f"{dd}.{m}.{y}"
        for g, gl in pairs:
            lines.append(f"<b>⚠️ Расписание на {ds} изменилось</b>")
            lines.append(f"<b>{escape(g)}</b>")
            lines.extend("• " + escape(x) for x in gl[:8])
            if len(gl) > 8:
                lines.append(f"… и ещё {len(gl) - 8} изм.")
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
        admin_chat_id = os.getenv("ADMIN_CHAT_ID")
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
            text = _render(payload)
            from schedule.models import Subscription
            if payload.get("type") == "new":
                names = [g for g, _d, _c in payload["imported"]]
            else:
                names = [g for pairs in payload["changes"].values()
                         for g, _ in pairs]
            chats = set(Subscription.objects.filter(
                group__name__in=names).values_list("chat_id", flat=True))
            if admin_chat_id:
                chats.add(admin_chat_id)
            if not chats:
                delivered += 1
                continue
            failed = _deliver(token, chats, text)
            if not failed:
                delivered += 1
            else:
                # неудача: вернуть в конец очереди, повтор на следующем проходе;
                # после 5 попыток выбрасываем, чтобы не клинить очередь
                payload["attempts"] = payload.get("attempts", 0) + 1
                if payload["attempts"] >= 5:
                    logger.error("drop notify after %s attempts",
                                 payload["attempts"])
                    delivered += 1
                else:
                    client.rpush("yadisk:notify",
                                 json.dumps(payload, ensure_ascii=False))
                    break
        self.stdout.write(f"доставлено событий: {delivered}")
