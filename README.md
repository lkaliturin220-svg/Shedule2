# 📅 Schedule — Расписание занятий

Django-приложение для просмотра расписания + Telegram-бот.  
Поддерживает формат файлов `studentam_ДД.ММ.ГГГГ.xlsx` (сложная таблица с 4 группами в строке, подгруппами, merged cells).

## ⚡ Быстрый старт (Docker)

```bash
cp .env.example .env
# Отредактируй .env — минимум SECRET_KEY и POSTGRES_PASSWORD

docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

Сайт: http://localhost:8000  
Панель загрузки: http://localhost:8000/admin-panel/  
Django Admin: http://localhost:8000/admin/

## 🔧 Ручная установка (Linux/Mac)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # заполни .env

python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
gunicorn -c gunicorn.conf.py config.wsgi:application

# В другом терминале — Telegram-бот:
python manage.py start_tgbot
```

## 📊 Формат файла расписания

Поддерживается файл вида `studentam_10.03.2026.xlsx`:
- Строка 1: `Расписание на ДД.ММ.ГГГГ`
- Лист называется днём недели (`Вторник`, `Среда`, …)
- До 4 групп по горизонтали, блоки по 6 колонок
- Автоматическое распознавание подгрупп

## 🏗️ Архитектура

```
schedule_final/
├── config/           # settings, urls, wsgi
├── schedule/
│   ├── parser.py     # парсер xlsx (рабочий!)
│   ├── models.py     # Group, Teacher, Subject, Lesson
│   ├── views.py      # views + REST API для бота
│   ├── admin.py
│   ├── urls.py
│   ├── static/       # CSS (темы) + JS
│   ├── templates/    # base, index, group, teacher, admin_panel, login
│   └── management/commands/start_tgbot.py
├── tgbot/bot.py      # aiogram 3, FSM, inline-клавиатуры
├── deploy/           # systemd unit-файлы
├── gunicorn.conf.py  # оптимизирован под высокий трафик
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## ⚙️ Оптимизация под нагрузку

| Компонент | Что сделано |
|-----------|------------|
| Gunicorn | gthread-воркеры, (2×CPU)+1, max_requests 2000 |
| Redis | Кэш страниц 120с, сессии, connection pool 50, LRU eviction |
| GZip | Встроенный middleware Django + WhiteNoise |
| WhiteNoise | Сжатая статика с manifest-хешами, долгий TTL |
| PostgreSQL | Индексы по (date,group), (date,teacher), (date,day_of_week) |
| select_related | FK в одном SQL-запросе |
| IGNORE_EXCEPTIONS | Не падает если Redis временно недоступен |

## 🤖 Telegram-бот

| Команда / кнопка | Описание |
|-----------------|----------|
| /start | Главное меню |
| 📚 Группы | Inline-список всех групп |
| 👨‍🏫 Преподаватели | Inline-список всех преподавателей |
| Выбор группы → | Расписание на сегодня + кнопки Сегодня/Завтра |

## 🌐 NPMplus / Nginx

Proxy Host → Forward to `web:8000`.  
HTTPS автоматически через Let's Encrypt.

## 🎨 Темы

Кнопка в навбаре переключает: 🖥️ Авто → 🌙 Тёмная → ☀️ Светлая.
