import asyncio
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Запустить Telegram-бота расписания"

    def handle(self, *args, **options):
        from tgbot.bot import main
        self.stdout.write("Запускаю Telegram-бота…")
        asyncio.run(main())
