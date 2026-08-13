# 📅 Расписание КГТТ

Неофициальный студенческий сайт расписания Кемеровского горнотехнического техникума.

🌐 **Сайт:** https://kemgtt.serverkiwi.ru  
👤 **Автор:** [@TIRED_Kiwi](https://t.me/TIRED_Kiwi)  
🤖 **Бот:** [@tiredkiwi_bot](https://t.me/tiredkiwi_bot)

---

## Возможности

- 📆 Расписание занятий по группам и преподавателям
- 📚 Конспекты и ДЗ — загрузка и просмотр по группам
- 🔐 Авторизация студентов по инвайт-коду
- 🔔 Telegram-уведомления об изменениях в расписании
- 💬 Обратная связь — баги и предложения
- 🛡️ Модерация конспектов для администратора

## Стек

| Компонент | Технология |
|-----------|-----------|
| Backend | Django 4.2 |
| База данных | PostgreSQL 16 |
| Кеш | Redis 7 |
| Сервер | Gunicorn + Nginx |
| Бот | aiogram 3 |
| Деплой | Docker Compose |

## Деплой

```bash
cp .env.example .env
# заполни .env

docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py createsuperuser
```

## Переменные окружения

Скопируй `.env.example` и заполни:

```
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=
DATABASE_URL=postgres://user:pass@db:5432/dbname
REDIS_URL=redis://redis:6379/1
TELEGRAM_BOT_TOKEN=
ADMIN_CHAT_ID=
YADISK_PUBLIC_KEY=      # публичная ссылка Яндекс.Диска с файлами studentam_*.xlsx
SCHEDULE_SYNC_INTERVAL=900
```

---

> Неофициальный студенческий проект — не является официальным ресурсом КГТТ
