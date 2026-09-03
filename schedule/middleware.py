"""Ленивая синхронизация: раз в SYNC_MAX_AGE секунд дешёвая проверка Я.Диска
в фоновом потоке; страница никогда не ждёт синк."""
import threading
import time
import logging

from django.conf import settings

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_last = [0.0]

SYNC_MAX_AGE = 15 * 60  # сек


def _maybe_sync():
    now = time.monotonic()
    with _lock:
        if now - _last[0] < SYNC_MAX_AGE:
            return
        _last[0] = now

    def run():
        try:
            from django.core.management import call_command
            call_command("sync_yadisk", verbosity=0)
        except Exception:
            logger.exception("lazy sync failed")

    threading.Thread(target=run, daemon=True, name="lazy-sync").start()


class LazySyncMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "SYNC_ON_REQUEST", False):
            try:
                _maybe_sync()
            except Exception:
                logger.exception("lazy sync trigger failed")
        return self.get_response(request)
