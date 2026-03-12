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
    1: "08:00–09:30", 2: "09:40–11:10", 3: "11:30–13:00",
    4: "13:20–14:50", 5: "15:00–16:30", 6: "16:40–18:10",
    7: "18:20–19:50", 8: "20:00–21:30",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def api_get(path: str, params: dict = None) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{BASE_URL}{path}", params=params) as r:
                return await r.json()
    except Exception as e:
        logger.error("API error %s: %s", path, e)
        return {}


def fmt_lessons(lessons: list, extra_field: str = "") -> str:
    if not lessons:
        return "📭 <i>Нет занятий на эту дату</i>"
    lines = []
    for l in lessons:
        time  = PAIR_TIMES.get(l["pair"], "")
        sub   = f" <b>(пг {l['subgroup']})</b>" if l.get("subgroup") else ""
        extra = f"\n   ↳ {l[extra_field]}" if extra_field and l.get(extra_field) else ""
        room  = f"  🚪 <code>{l['room']}</code>" if l.get("room") else ""
        lines.append(f"<b>{l['pair']}</b>{sub} <i>{time}</i>\n   {l['subject']}{room}{extra}")
    return "\n\n".join(lines)


def dates_kb(dates: list[str], prefix: str, entity: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора даты."""
    rows = []
    for d in dates[:10]:  # не больше 10 дат
        rows.append([InlineKeyboardButton(text=d, callback_data=f"{prefix}:{entity}:{d}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Группы"),   KeyboardButton(text="👨‍🏫 Преподаватели")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


# ── FSM States ───────────────────────────────────────────────────────────────

class S(StatesGroup):
    group_list   = State()
    teacher_list = State()


# ── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет!</b>\n\nЯ бот расписания занятий.\nВыбери, что хочешь посмотреть:",
        reply_markup=main_kb(),
        parse_mode="HTML",
    )


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📋 <b>Команды:</b>\n"
        "/start — главное меню\n"
        "/groups — список групп\n"
        "/teachers — список преподавателей\n\n"
        "Или нажми кнопку 👇",
        parse_mode="HTML",
    )


# ── Списки групп ─────────────────────────────────────────────────────────────

@router.message(Command("groups"))
@router.message(F.text == "📚 Группы")
async def cmd_groups(message: Message):
    data   = await api_get("/api/groups/")
    groups = data.get("groups", [])
    if not groups:
        return await message.answer("Нет данных о группах.")

    rows = []
    row  = []
    for g in groups:
        row.append(InlineKeyboardButton(text=g, callback_data=f"grp_dates:{g}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)

    await message.answer(
        "📚 <b>Выбери группу:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


# ── Списки преподавателей ────────────────────────────────────────────────────

@router.message(Command("teachers"))
@router.message(F.text == "👨‍🏫 Преподаватели")
async def cmd_teachers(message: Message):
    data     = await api_get("/api/teachers/")
    teachers = data.get("teachers", [])
    if not teachers:
        return await message.answer("Нет данных о преподавателях.")

    rows = [[
        InlineKeyboardButton(text=t["name"], callback_data=f"tch_dates:{t['id']}")
    ] for t in teachers]

    await message.answer(
        "👨‍🏫 <b>Выбери преподавателя:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


# ── Callback: выбрать дату для группы ───────────────────────────────────────

@router.callback_query(F.data.startswith("grp_dates:"))
async def cb_grp_dates(call: CallbackQuery):
    group = call.data.split(":", 1)[1]
    today = str(date.today())
    # Получаем расписание на сегодня сразу, и предлагаем другие даты
    data    = await api_get(f"/api/schedule/group/{group}/", {"date": today})
    lessons = data.get("lessons", [])
    text    = f"📚 <b>{group}</b> — {today}\n\n{fmt_lessons(lessons, 'teacher')}"

    # Кнопки: сегодня / завтра / другие даты из БД
    rows = [
        [InlineKeyboardButton(text="📅 Сегодня",  callback_data=f"grp:{group}:{today}"),
         InlineKeyboardButton(text="📅 Завтра",   callback_data=f"grp:{group}:{str(date.today()+timedelta(days=1))}")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("grp:"))
async def cb_grp(call: CallbackQuery):
    _, group, d = call.data.split(":", 2)
    data    = await api_get(f"/api/schedule/group/{group}/", {"date": d})
    lessons = data.get("lessons", [])
    text    = f"📚 <b>{group}</b> — {d}\n\n{fmt_lessons(lessons, 'teacher')}"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


# ── Callback: выбрать дату для преподавателя ─────────────────────────────────

@router.callback_query(F.data.startswith("tch_dates:"))
async def cb_tch_dates(call: CallbackQuery):
    pk    = call.data.split(":", 1)[1]
    today = str(date.today())
    data  = await api_get(f"/api/schedule/teacher/{pk}/", {"date": today})
    name  = data.get("teacher", pk)
    text  = f"👨‍🏫 <b>{name}</b> — {today}\n\n{fmt_lessons(data.get('lessons', []), 'group')}"

    rows = [
        [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"tch:{pk}:{today}"),
         InlineKeyboardButton(text="📅 Завтра",  callback_data=f"tch:{pk}:{str(date.today()+timedelta(days=1))}")],
    ]
    await call.message.answer(text, parse_mode="HTML",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("tch:"))
async def cb_tch(call: CallbackQuery):
    _, pk, d = call.data.split(":", 2)
    data = await api_get(f"/api/schedule/teacher/{pk}/", {"date": d})
    text = f"👨‍🏫 <b>{data.get('teacher','')}</b> — {d}\n\n{fmt_lessons(data.get('lessons',[]),'group')}"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан!")
        return
    logger.info("Telegram bot starting…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
