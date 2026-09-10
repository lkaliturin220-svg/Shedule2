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
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.getenv("SCHEDULE_API_URL", "http://127.0.0.1:8000")

_proxy   = os.getenv("PROXY_URL", "")
bot      = Bot(token=TOKEN, session=AiohttpSession(proxy=_proxy) if _proxy else None)
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


def _groups_kb(prefix: str, groups: list, with_date: bool = True) -> InlineKeyboardMarkup:
    """Сетка кнопок 3 в ряд. with_date — дописать сегодняшнюю дату в callback."""
    rows, row = [], []
    for g in groups:
        data = f"{prefix}:{g}:{date.today()}" if with_date else f"{prefix}:{g}"
        row.append(InlineKeyboardButton(text=g, callback_data=data))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
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


async def _is_chat_admin(message: Message) -> bool:
    """В личке — сам хозяин; в группах — только администраторы чата."""
    if message.chat.type == "private":
        return True
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception as e:
        logger.warning("get_chat_member error: %s", e)
        return False


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
        "👑 Админ группового чата? Напиши <b>/bind</b> — привяжу чат к расписанию "
        "одной группы (можно в топик форума).\n\n"
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
        "<b>Для групповых чатов (админам):</b>\n"
        "/bind — привязать чат к расписанию одной группы\n"
        "   в чате-форуме привяжет <b>текущий топик</b> к своей группе\n"
        "/settopic — слать обновления в этот топик (форум-группы)\n"
        "/binding — текущая привязка чата (и список топиков)\n"
        "/unbind — отвязать чат (в форуме — текущий топик)\n\n"
        "📢 Привязанный чат получает обновления <b>только своей группы</b>.\n"
        "🔔 Подписка из топика форума придёт обратно в этот же топик.",
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

    await message.answer(
        "📚 <b>Выбери группу:</b>",
        reply_markup=_groups_kb("grp", groups),
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


def _add_subscription(chat_id: int, group_name: str, thread_id: int | None = None) -> bool:
    try:
        from schedule.models import Group, Subscription
        group = Group.get_or_create_by_name(group_name)
        _, created = Subscription.objects.update_or_create(
            chat_id=chat_id, group=group,
            defaults={"thread_id": thread_id},
        )
        return True
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
    chat    = call.message.chat
    chat_id = chat.id
    # В форум-чате запоминаем топик, из которого подписались (в General — None)
    thread  = getattr(call.message, "message_thread_id", None) if chat.is_forum else None

    loop = asyncio.get_event_loop()
    ok   = await loop.run_in_executor(None, _add_subscription, chat_id, group, thread)

    if ok:
        where = f" в топик <b>#{thread}</b>" if thread else ""
        await call.answer(f"✅ Подписка на группу {group} оформлена!", show_alert=True)
        await call.message.answer(
            f"🔔 <b>Подписка оформлена!</b>\n\n"
            f"Группа: <b>{group}</b>\n\n"
            f"Как только появится новое расписание — пришлю автоматически{where}.\n"
            f"Управление подписками: кнопка <b>🔔 Мои подписки</b>",
            parse_mode="HTML",
        )
    else:
        await call.answer(f"⚠️ Не смог оформить подписку на {group}", show_alert=True)


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


# ── Привязка чата к расписанию одной группы (+ топик) ────────────────────────

def _bind_chat(chat_id: int, group_name: str, thread_id, user_id: int) -> bool:
    try:
        from schedule.models import ChatBinding, Group
        group = Group.get_or_create_by_name(group_name)
        ChatBinding.objects.update_or_create(
            chat_id=chat_id,
            defaults={"group": group, "thread_id": thread_id, "created_by": user_id},
        )
        return True
    except Exception as e:
        logger.error("DB error bind_chat: %s", e)
        return False


def _bind_topic(chat_id: int, thread_id: int, group_name: str, user_id: int) -> bool:
    try:
        from schedule.models import ChatTopicBinding, Group
        group = Group.get_or_create_by_name(group_name)
        ChatTopicBinding.objects.update_or_create(
            chat_id=chat_id, thread_id=thread_id,
            defaults={"group": group, "created_by": user_id},
        )
        return True
    except Exception as e:
        logger.error("DB error bind_topic: %s", e)
        return False


def _set_thread(chat_id: int, thread_id: int) -> bool:
    try:
        from schedule.models import ChatBinding
        updated = ChatBinding.objects.filter(chat_id=chat_id).update(thread_id=thread_id)
        return updated > 0
    except Exception as e:
        logger.error("DB error set_thread: %s", e)
        return False


@router.message(Command("bind"))
async def cmd_bind(message: Message):
    if not await _is_chat_admin(message):
        return await message.answer(
            "🔒 Привязывать чат к группе могут только админы чата.",
        )
    groups = (await api_get("/api/groups/")).get("groups", [])
    if not groups:
        return await message.answer("⚠️ Нет данных о группах. Попробуй позже.")

    hint = ""
    if message.chat.is_forum:
        if getattr(message, "message_thread_id", None):
            hint = ("\n\nЭтот чат — форум: привяжу <b>именно этот топик</b> "
                    "к выбранной группе (другие топики — свои).")
        else:
            hint = ("\n\nЭто чат-форум: напиши /bind внутри нужного топика — привяжу топик к группе.\n"
                    "Или выбери сейчас — привяжется весь чат (Общий).")

    await message.answer(
        "📌 <b>Какую группу расписания привязать к этому чату?</b>\n"
        "Обновления будут приходить <b>только по ней</b>." + hint,
        reply_markup=_groups_kb("bind", groups, with_date=False),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("bind:"))
async def cb_bind(call: CallbackQuery):
    group  = call.data.split(":", 1)[1]
    chat   = call.message.chat
    thread = getattr(call.message, "message_thread_id", None)

    loop = asyncio.get_event_loop()
    if chat.is_forum and thread:
        ok = await loop.run_in_executor(None, _bind_topic, chat.id, thread, group, call.from_user.id)
    else:
        ok = await loop.run_in_executor(None, _bind_chat, chat.id, group, thread, call.from_user.id)
    if not ok:
        return await call.answer("⚠️ Ошибка базы — попробуй позже", show_alert=True)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if chat.is_forum and thread:
        text = (
            f"✅ <b>Топик #{thread} привязан к группе {group}</b>\n\n"
            f"Обновления по группе <b>{group}</b> будут приходить в этот топик.\n"
            f"Другие топики можно привязать к своим группам: /bind внутри них.\n"
            f"Список привязок — /binding, отвязать этот топик — /unbind."
        )
    elif chat.is_forum and not thread:
        text = (
            f"✅ <b>Чат привязан к группе {group}</b>\n\n"
            f"Это чат-форум: обновления пойдут в «Общий».\n"
            f"Хочешь отдельные группы по топикам — /bind внутри каждого топика."
        )
    else:
        where = "в этот топик" if thread else "сюда"
        text = (
            f"✅ <b>Чат привязан к группе {group}</b>\n\n"
            f"Обновления — <b>только по этой группе</b>, пришлю {where}.\n"
            f"Сменить группу — /bind, топик — /settopic, отвязать — /unbind."
        )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()


@router.message(Command("settopic"))
async def cmd_settopic(message: Message):
    if not await _is_chat_admin(message):
        return await message.answer("🔒 Менять топик могут только админы чата.")
    if not message.chat.is_forum:
        return await message.answer(
            "Этот чат — не форум: топиков нет, обновления идут в общий поток.",
        )
    thread = getattr(message, "message_thread_id", None)
    if thread is None:
        return await message.answer(
            "Напиши эту команду внутри нужного топика — я привяжу его.\n"
            "(В форуме проще: /bind внутри топика привяжет его к группе.)",
        )
    loop = asyncio.get_event_loop()
    ok   = await loop.run_in_executor(None, _set_thread, message.chat.id, thread)
    if ok:
        await message.answer(
            "✅ Обновления расписания будут приходить в этот топик.\n"
            "Хочешь разные группы по топикам — /bind внутри каждого топика.",
        )
    else:
        await message.answer("⚠️ Сначала привяжи чат к группе: /bind")


@router.message(Command("binding"))
async def cmd_binding(message: Message):
    def _get_all():
        from schedule.models import ChatBinding, ChatTopicBinding
        b = ChatBinding.objects.filter(chat_id=message.chat.id).select_related("group").first()
        topics = list(ChatTopicBinding.objects.filter(chat_id=message.chat.id)
                      .select_related("group").order_by("thread_id"))
        return b, topics

    loop = asyncio.get_event_loop()
    b, topics = await loop.run_in_executor(None, _get_all)
    if not b and not topics:
        return await message.answer(
            "Этот чат не привязан. /bind — привязать чат или топик к расписанию группы.",
        )

    lines = ["📌 <b>Привязки этого чата:</b>\n"]
    if b:
        topic = f", топик #{b.thread_id}" if b.thread_id else ""
        lines.append(f"• Весь чат → <b>{b.group.name}</b>{topic}")
    for t in topics:
        lines.append(f"• Топик #{t.thread_id} → <b>{t.group.name}</b>")
    lines.append(
        "\nОбновления приходят только по привязанным группам.\n"
        "/bind — привязать/сменить (в форуме — текущий топик), /unbind — отвязать."
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("unbind"))
async def cmd_unbind(message: Message):
    if not await _is_chat_admin(message):
        return await message.answer("🔒 Отвязывать чат могут только админы чата.")

    chat    = message.chat
    thread  = getattr(message, "message_thread_id", None)

    def _del():
        from schedule.models import ChatBinding, ChatTopicBinding
        if chat.is_forum and thread:
            deleted, _ = ChatTopicBinding.objects.filter(chat_id=chat.id, thread_id=thread).delete()
            return deleted, "топик"
        deleted, _ = ChatBinding.objects.filter(chat_id=chat.id).delete()
        return deleted, "чат"

    loop            = asyncio.get_event_loop()
    deleted, target = await loop.run_in_executor(None, _del)
    if deleted:
        await message.answer(
            f"✅ {target.capitalize()} отвязан" + (" (в форуме — текущий топик)." if chat.is_forum else " — обновления больше не приходят."),
        )
    else:
        await message.answer(
            "Этот топик и не был привязан." if (chat.is_forum and thread) else "Этот чат и не был привязан.",
        )


# ── Main ──────────────────────────────────────────────────────────────────────

async def _setup_commands():
    """Регистрация команд — они появятся в меню Telegram (кнопка «Меню»)."""
    from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats

    private = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="groups", description="📚 Расписание групп"),
        BotCommand(command="teachers", description="👨‍🏫 Расписание преподавателей"),
        BotCommand(command="subscribe", description="🔔 Мои подписки"),
        BotCommand(command="unsubscribe", description="🔕 Отписаться от всех"),
        BotCommand(command="help", description="ℹ️ Помощь"),
    ]
    group = [
        BotCommand(command="bind", description="📌 Привязать чат/топик к группе"),
        BotCommand(command="binding", description="📌 Текущие привязки чата"),
        BotCommand(command="settopic", description="🧵 Слать обновления в этот топик"),
        BotCommand(command="unbind", description="✖️ Отвязать чат/топик"),
        BotCommand(command="groups", description="📚 Расписание групп"),
        BotCommand(command="help", description="ℹ️ Помощь"),
    ]
    await bot.set_my_commands(private, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(group, scope=BotCommandScopeAllGroupChats())


async def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан!")
        return
    _setup_django()
    try:
        await _setup_commands()
        logger.info("Команды зарегистрированы (личка + группы)")
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)
    logger.info("Telegram bot starting…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
