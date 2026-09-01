"""
Telegram-бот расписания (aiogram 3).
Запуск через management command: python manage.py start_tgbot
"""
import asyncio
import logging
import os
from datetime import date, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.getenv("SCHEDULE_API_URL", "http://127.0.0.1:8000")

bot     = Bot(token=TOKEN)
storage = MemoryStorage()
dp      = Dispatcher(storage=storage)
router  = Router()
dp.include_router(router)

PAIR_TIMES = {
    1: "08:30–10:00", 2: "10:20–11:50", 3: "12:10–13:40",
    4: "14:00–15:30", 5: "15:40–17:10", 6: "17:15–18:45",
    7: "19:00–20:30", 8: "20:00–21:30",
}

WEEKDAYS_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг",     4: "Пятница", 5: "Суббота", 6: "Воскресенье",
}


# ── Django ORM (используется для подписок) ───────────────────────────────────

def _setup_django():
    import django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        django.setup()
    except RuntimeError:
        pass  # уже инициализирован


# ── Helpers ──────────────────────────────────────────────────────────────────

async def api_get(path: str, params: dict = None) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{BASE_URL}{path}", params=params) as r:
                return await r.json()
    except Exception as e:
        logger.error("API error %s: %s", path, e)
        return {}


def fmt_date_ru(d: str) -> str:
    """2026-03-14 → Пятница, 14 марта 2026"""
    try:
        dt = date.fromisoformat(d)
        months = ["января","февраля","марта","апреля","мая","июня",
                  "июля","августа","сентября","октября","ноября","декабря"]
        return f"{WEEKDAYS_RU[dt.weekday()]}, {dt.day} {months[dt.month-1]} {dt.year}"
    except Exception:
        return d


def fmt_lessons(lessons: list, extra_field: str = "") -> str:
    if not lessons:
        return "📭 <i>Занятий нет</i>"
    lines = []
    for l in lessons:
        time  = PAIR_TIMES.get(l["pair"], "")
        sub   = f" <b>(пг {l['subgroup']})</b>" if l.get("subgroup") else ""
        extra = f"\n   ↳ {l[extra_field]}" if extra_field and l.get(extra_field) else ""
        room  = f"  🚪 <code>{l['room']}</code>" if l.get("room") else ""
        lines.append(f"<b>{l['pair']} пара</b>{sub}  <i>{time}</i>\n   📖 {l['subject']}{room}{extra}")
    return "\n\n".join(lines)


def date_nav_kb(prefix: str, key: str, d: str, extra_rows: list = None) -> InlineKeyboardMarkup:
    """Кнопки навигации по датам: ← предыдущий день | сегодня | следующий день →"""
    dt   = date.fromisoformat(d)
    prev = str(dt - timedelta(days=1))
    nxt  = str(dt + timedelta(days=1))
    today = str(date.today())
    rows = [
        [
            InlineKeyboardButton(text="◀️ Пред. день", callback_data=f"{prefix}:{key}:{prev}"),
            InlineKeyboardButton(text="Сегодня 📅",   callback_data=f"{prefix}:{key}:{today}"),
            InlineKeyboardButton(text="След. день ▶️", callback_data=f"{prefix}:{key}:{nxt}"),
        ],
    ]
    if extra_rows:
        rows.extend(extra_rows)
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Группы"),        KeyboardButton(text="👨‍🏫 Преподаватели")],
            [KeyboardButton(text="🔔 Мои подписки"),  KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


async def safe_edit(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    """Редактировать текущее сообщение. Если не получается — отправить новое."""
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=markup)


# ── FSM States ───────────────────────────────────────────────────────────────

class S(StatesGroup):
    group_list   = State()
    teacher_list = State()


# ── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет!</b>\n\n"
        "Я бот расписания занятий КемГТТ.\n\n"
        "📚 <b>Группы</b> — расписание для студентов\n"
        "👨‍🏫 <b>Преподаватели</b> — расписание для педагогов\n"
        "🔔 <b>Мои подписки</b> — авто-уведомления о новом расписании\n\n"
        "Выбери нужный раздел:",
        reply_markup=main_kb(),
        parse_mode="HTML",
    )


# ── Главное меню (callback) ───────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer(
        "🏠 <b>Главное меню</b>\n\nВыбери нужный раздел:",
        reply_markup=main_kb(),
        parse_mode="HTML",
    )
    await call.answer()


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📋 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Нажми <b>📚 Группы</b> — выбери свою группу\n"
        "2️⃣ Листай расписание кнопками <b>◀️ Пред. день</b> и <b>след. день ▶️</b>\n"
        "3️⃣ Нажми <b>🔔 Подписаться</b> — получай уведомления автоматически\n\n"
        "👨‍🏫 Для преподавателей — кнопка <b>👨‍🏫 Преподаватели</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/groups — список групп\n"
        "/teachers — список преподавателей\n"
        "/subscribe — мои подписки\n"
        "/unsubscribe — отписаться от всех\n\n"
        "📢 Бот работает в групповых чатах — добавь и напиши /subscribe",
        parse_mode="HTML",
    )


# ── Список групп ──────────────────────────────────────────────────────────────

@router.message(Command("groups"))
@router.message(F.text == "📚 Группы")
async def cmd_groups(message: Message):
    data   = await api_get("/api/groups/")
    groups = data.get("groups", [])
    if not groups:
        return await message.answer("⚠️ Нет данных о группах. Попробуй позже.")

    rows = []
    row  = []
    for g in groups:
        row.append(InlineKeyboardButton(text=g, callback_data=f"grp:{g}:{date.today()}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)

    await message.answer(
        "📚 <b>Выбери группу:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


# ── Список преподавателей ─────────────────────────────────────────────────────

@router.message(Command("teachers"))
@router.message(F.text == "👨‍🏫 Преподаватели")
async def cmd_teachers(message: Message):
    data     = await api_get("/api/teachers/")
    teachers = data.get("teachers", [])
    if not teachers:
        return await message.answer("⚠️ Нет данных о преподавателях. Попробуй позже.")

    rows = []
    row  = []
    for t in teachers:
        row.append(InlineKeyboardButton(text=t["name"], callback_data=f"tch:{t['id']}:{date.today()}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)

    await message.answer(
        "👨‍🏫 <b>Выбери преподавателя:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


# ── Расписание группы (с навигацией) ─────────────────────────────────────────

@router.callback_query(F.data.startswith("grp:"))
async def cb_grp(call: CallbackQuery):
    _, group, d = call.data.split(":", 2)
    data    = await api_get(f"/api/schedule/group/{group}/", {"date": d})
    lessons = data.get("lessons", [])

    text = (
        f"📚 <b>Группа {group}</b>\n"
        f"📅 {fmt_date_ru(d)}\n"
        f"{'─' * 28}\n\n"
        f"{fmt_lessons(lessons, 'teacher')}"
    )

    sub_row = [[InlineKeyboardButton(
        text="🔔 Подписаться на уведомления",
        callback_data=f"sub_add:{group}"
    )]]

    await safe_edit(call, text, date_nav_kb("grp", group, d, sub_row))
    await call.answer()


# ── Расписание преподавателя (с навигацией) ───────────────────────────────────

@router.callback_query(F.data.startswith("tch:"))
async def cb_tch(call: CallbackQuery):
    _, pk, d = call.data.split(":", 2)
    data  = await api_get(f"/api/schedule/teacher/{pk}/", {"date": d})
    name  = data.get("teacher", pk)

    text = (
        f"👨‍🏫 <b>{name}</b>\n"
        f"📅 {fmt_date_ru(d)}\n"
        f"{'─' * 28}\n\n"
        f"{fmt_lessons(data.get('lessons', []), 'group')}"
    )

    await safe_edit(call, text, date_nav_kb("tch", pk, d))
    await call.answer()


# ── Подписки ──────────────────────────────────────────────────────────────────

def _get_subscriptions(chat_id: int) -> list[str]:
    try:
        from schedule.models import Subscription
        return list(Subscription.objects.filter(chat_id=chat_id).values_list("group__name", flat=True))
    except Exception as e:
        logger.error("DB error get_subscriptions: %s", e)
        return []


def _add_subscription(chat_id: int, group_name: str) -> bool:
    try:
        from schedule.models import Group, Subscription
        group = Group.get_or_create_by_name(group_name)
        _, created = Subscription.objects.get_or_create(chat_id=chat_id, group=group)
        return created
    except Exception as e:
        logger.error("DB error add_subscription: %s", e)
        return False


def _remove_subscription(chat_id: int, group_name: str) -> bool:
    try:
        from schedule.models import Group, Subscription
        deleted, _ = Subscription.objects.filter(chat_id=chat_id, group__name=group_name).delete()
        return deleted > 0
    except Exception as e:
        logger.error("DB error remove_subscription: %s", e)
        return False


@router.callback_query(F.data.startswith("sub_add:"))
async def cb_sub_add(call: CallbackQuery):
    group   = call.data.split(":", 1)[1]
    chat_id = call.message.chat.id

    loop    = asyncio.get_event_loop()
    created = await loop.run_in_executor(None, _add_subscription, chat_id, group)

    if created:
        await call.answer(f"✅ Подписка на группу {group} оформлена!", show_alert=True)
        await call.message.answer(
            f"🔔 <b>Подписка оформлена!</b>\n\n"
            f"Группа: <b>{group}</b>\n\n"
            f"Как только появится новое расписание — пришлю сюда автоматически.\n"
            f"Управление подписками: кнопка <b>🔔 Мои подписки</b>",
            parse_mode="HTML",
        )
    else:
        await call.answer(f"Ты уже подписан на группу {group}", show_alert=True)


@router.callback_query(F.data.startswith("sub_del:"))
async def cb_sub_del(call: CallbackQuery):
    group   = call.data.split(":", 1)[1]
    chat_id = call.message.chat.id

    loop    = asyncio.get_event_loop()
    removed = await loop.run_in_executor(None, _remove_subscription, chat_id, group)

    if removed:
        await call.answer(f"❌ Отписался от группы {group}", show_alert=True)
    else:
        await call.answer("Подписка не найдена", show_alert=True)

    await show_subscriptions_edit(call)


async def show_subscriptions_edit(call: CallbackQuery):
    """Обновить список подписок прямо в текущем сообщении."""
    chat_id = call.message.chat.id
    loop    = asyncio.get_event_loop()
    subs    = await loop.run_in_executor(None, _get_subscriptions, chat_id)

    if not subs:
        await safe_edit(
            call,
            "🔕 <b>Нет активных подписок</b>\n\n"
            "Выбери группу → нажми <b>🔔 Подписаться на уведомления</b>",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📚 Выбрать группу", callback_data="go_groups")
            ]])
        )
        return

    rows = []
    for g in subs:
        rows.append([
            InlineKeyboardButton(text=f"📚 {g}", callback_data=f"grp:{g}:{date.today()}"),
            InlineKeyboardButton(text="❌ Отписаться", callback_data=f"sub_del:{g}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])

    await safe_edit(
        call,
        f"🔔 <b>Мои подписки ({len(subs)}):</b>\n\n"
        "Нажми 📚 — посмотреть расписание\n"
        "Нажми ❌ — отписаться",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "go_groups")
async def cb_go_groups(call: CallbackQuery):
    await call.message.delete()
    await cmd_groups(call.message)
    await call.answer()


async def show_subscriptions_new(message: Message, chat_id: int):
    """Отправить список подписок новым сообщением."""
    loop = asyncio.get_event_loop()
    subs = await loop.run_in_executor(None, _get_subscriptions, chat_id)

    if not subs:
        await message.answer(
            "🔕 <b>Нет активных подписок</b>\n\n"
            "Выбери группу → нажми <b>🔔 Подписаться на уведомления</b>",
            parse_mode="HTML",
        )
        return

    rows = []
    for g in subs:
        rows.append([
            InlineKeyboardButton(text=f"📚 {g}", callback_data=f"grp:{g}:{date.today()}"),
            InlineKeyboardButton(text="❌ Отписаться", callback_data=f"sub_del:{g}"),
        ])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])

    await message.answer(
        f"🔔 <b>Мои подписки ({len(subs)}):</b>\n\n"
        "Нажми 📚 — посмотреть расписание\n"
        "Нажми ❌ — отписаться",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


@router.message(Command("subscribe"))
@router.message(F.text == "🔔 Мои подписки")
async def cmd_subscriptions(message: Message):
    await show_subscriptions_new(message, message.chat.id)


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    chat_id = message.chat.id
    try:
        from schedule.models import Subscription
        deleted, _ = Subscription.objects.filter(chat_id=chat_id).delete()
        if deleted:
            await message.answer("✅ Отписался от всех групп.")
        else:
            await message.answer("У тебя нет активных подписок.")
    except Exception as e:
        logger.error("unsubscribe error: %s", e)
        await message.answer("⚠️ Ошибка при отписке. Попробуй позже.")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан!")
        return
    _setup_django()
    logger.info("Telegram bot starting…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

