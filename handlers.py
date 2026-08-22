from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

import config
import db

router = Router()

BTN_PARTNER = "👤 Собеседник"
BTN_PROFILE = "ℹ️ Моя анкета"
BTN_EDIT = "📝 Изменить анкету"
BTN_END = "🚫 Завершить общение"
BTN_OFF = "🔕 Отключить анкету"
BTN_ON = "🔔 Включить анкету"

MENU_BUTTONS = {BTN_PARTNER, BTN_PROFILE, BTN_EDIT, BTN_END, BTN_OFF, BTN_ON}

PARTNER_LEFT_MESSAGE = "Твой собеседник завершил общение. Новый собеседник появится завтра в 00:00."


class Reg(StatesGroup):
    full_name = State()
    role = State()
    group = State()


def today_str() -> str:
    return datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")


def format_user(user: dict) -> str:
    group = f"\nГруппа: {user['group_num']}" if user.get("group_num") else ""
    return f"👤 {user['first_name']} {user['last_name']}\nРоль: {user['role']}{group}"


def role_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Куратор"), KeyboardButton(text="Первокурсник")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_keyboard(user: dict) -> ReplyKeyboardMarkup:
    toggle = BTN_OFF if user.get("active", 1) else BTN_ON
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PARTNER)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_EDIT)],
            [KeyboardButton(text=BTN_END)],
            [KeyboardButton(text=toggle)],
        ],
        resize_keyboard=True,
    )


async def show_profile(msg: Message, user: dict) -> None:
    status = "активна" if user.get("active", 1) else "отключена"
    await msg.answer(
        f"Твоя анкета:\n\n{format_user(user)}\n\nСтатус: {status}\n\n"
        "Используй кнопки ниже, чтобы посмотреть собеседника, "
        "изменить анкету или завершить общение.",
        reply_markup=main_keyboard(user),
    )


async def show_partner(msg: Message) -> None:
    partner = db.get_active_partner(msg.from_user.id, today_str())
    if not partner:
        await msg.answer("Сейчас у тебя нет собеседника. Новый появится в 00:00.")
        return
    await msg.answer(f"Твой собеседник на сегодня:\n\n{format_user(partner)}")


async def do_end(msg: Message) -> None:
    partner = db.get_active_partner(msg.from_user.id, today_str())
    if not partner:
        await msg.answer("У тебя нет активного собеседника.")
        return
    db.end_pair(msg.from_user.id, today_str())
    await msg.answer("Общение завершено. Новый собеседник появится завтра в 00:00.")
    await msg.bot.send_message(
        partner["id"],
        PARTNER_LEFT_MESSAGE,
    )


async def do_toggle(msg: Message) -> None:
    user = db.get_user(msg.from_user.id)
    if not user:
        return
    if user.get("active", 1):
        partner = db.get_active_partner(msg.from_user.id, today_str())
        if partner:
            warn = "Твой текущий собеседник будет сброшен, и ты не будешь получать новых собеседников, пока анкета отключена."
        else:
            warn = "Ты не будешь получать новых собеседников, пока анкета отключена."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да, отключить", callback_data="confirm_off"),
                    InlineKeyboardButton(text="Отмена", callback_data="cancel_off"),
                ],
            ],
        )
        await msg.answer(
            f"⚠️ Ты собираешься отключить анкету.\n\n{warn}\n\nОтключить анкету?",
            reply_markup=kb,
        )
    else:
        db.set_active(msg.from_user.id, True)
        await msg.answer(
            "Анкета включена. Ты снова участвуешь в подборе — новый собеседник появится в 00:00.",
            reply_markup=main_keyboard(db.get_user(msg.from_user.id)),
        )


async def start_registration(msg: Message, state: FSMContext) -> None:
    await msg.answer(
        "Введи имя и фамилию через пробел (например: Иван Иванов):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Reg.full_name)


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    user = db.get_user(msg.from_user.id)
    if user:
        await show_profile(msg, user)
    else:
        await msg.answer(
            "Привет! Давай зарегистрируемся.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await start_registration(msg, state)


@router.message(Command("register"))
async def cmd_register(msg: Message, state: FSMContext) -> None:
    await start_registration(msg, state)


@router.message(Command("cancel"), StateFilter(Reg))
async def cmd_cancel(msg: Message, state: FSMContext) -> None:
    await state.clear()
    user = db.get_user(msg.from_user.id)
    if user:
        await show_profile(msg, user)
    else:
        await msg.answer("Регистрация отменена. Нажми /start, чтобы начать.")


@router.message(Command("profile"))
async def cmd_profile(msg: Message) -> None:
    user = db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Ты ещё не зарегистрирован. Нажми /start.")
        return
    await show_profile(msg, user)


@router.message(Command("partner"))
async def cmd_partner(msg: Message) -> None:
    user = db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Ты ещё не зарегистрирован. Нажми /start.")
        return
    await show_partner(msg)


@router.message(Command("end"))
async def cmd_end(msg: Message) -> None:
    user = db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Ты ещё не зарегистрирован. Нажми /start.")
        return
    await do_end(msg)


@router.message(StateFilter(Reg.full_name), F.text)
async def reg_full_name(msg: Message, state: FSMContext) -> None:
    parts = msg.text.strip().split()
    if len(parts) < 2:
        await msg.answer(
            "Пожалуйста, укажи и имя, и фамилию через пробел (например: Иван Иванов)."
        )
        return
    await state.update_data(
        first_name=parts[0],
        last_name=" ".join(parts[1:]),
    )
    await msg.answer("Кто ты?", reply_markup=role_keyboard())
    await state.set_state(Reg.role)


@router.message(StateFilter(Reg.role), F.text)
async def reg_role(msg: Message, state: FSMContext) -> None:
    text = msg.text.strip().lower()
    if text == "куратор":
        await state.update_data(role="Куратор", group_num=None)
        await finish_registration(msg, state)
    elif text == "первокурсник":
        await state.update_data(role="Первокурсник")
        await msg.answer(
            "Введи номер своей группы (например, М-101):",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(Reg.group)
    else:
        await msg.answer("Пожалуйста, выбери вариант из кнопок.", reply_markup=role_keyboard())


@router.message(StateFilter(Reg.group), F.text)
async def reg_group(msg: Message, state: FSMContext) -> None:
    await state.update_data(group_num=msg.text.strip())
    await finish_registration(msg, state)


async def finish_registration(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    db.add_user(
        msg.from_user.id,
        data["first_name"],
        data["last_name"],
        data["role"],
        data.get("group_num"),
    )
    await state.clear()
    await msg.answer(
        "✅ Регистрация завершена!\n\n"
        "Каждый день в 00:00 тебе будет подобран случайный собеседник. "
        "Просто пиши сообщения — они будут пересылаться ему.",
        reply_markup=main_keyboard(db.get_user(msg.from_user.id)),
    )
    await show_profile(msg, db.get_user(msg.from_user.id))


@router.message(StateFilter(None), F.text.in_(MENU_BUTTONS))
async def on_menu_button(msg: Message, state: FSMContext) -> None:
    if not db.get_user(msg.from_user.id):
        await msg.answer("Сначала зарегистрируйся — нажми /start.")
        return
    if msg.text == BTN_PARTNER:
        await show_partner(msg)
    elif msg.text == BTN_PROFILE:
        await show_profile(msg, db.get_user(msg.from_user.id))
    elif msg.text == BTN_EDIT:
        await start_registration(msg, state)
    elif msg.text == BTN_END:
        await do_end(msg)
    elif msg.text in (BTN_OFF, BTN_ON):
        await do_toggle(msg)


@router.callback_query(F.data == "confirm_off")
async def cb_confirm_off(cb: CallbackQuery) -> None:
    user = db.get_user(cb.from_user.id)
    if not user:
        await cb.answer("Анкета не найдена.")
        return
    partner = db.get_active_partner(cb.from_user.id, today_str())
    db.set_active(cb.from_user.id, False)
    if partner:
        db.end_pair(cb.from_user.id, today_str())
        await cb.bot.send_message(
            partner["id"],
            PARTNER_LEFT_MESSAGE,
        )
    await cb.answer()
    await cb.message.edit_text("✅ Анкета отключена. Ты больше не участвуешь в подборе пар.")
    await cb.message.answer(
        "Чтобы вернуться, нажми «🔔 Включить анкету».",
        reply_markup=main_keyboard(db.get_user(cb.from_user.id)),
    )


@router.callback_query(F.data == "cancel_off")
async def cb_cancel_off(cb: CallbackQuery) -> None:
    await cb.answer("Отменено.")
    await cb.message.edit_text("Отключение анкеты отменено.")


@router.message(StateFilter(None), F.text)
async def chat_message(msg: Message) -> None:
    if msg.text.startswith("/") or msg.text in MENU_BUTTONS:
        return

    user = db.get_user(msg.from_user.id)
    if not user:
        await msg.answer("Сначала зарегистрируйся — нажми /start.")
        return

    partner = db.get_active_partner(msg.from_user.id, today_str())
    if not partner:
        await msg.answer(
            "Сейчас у тебя нет собеседника. Новый появится в 00:00. "
            "Используй кнопки внизу для остальных действий."
        )
        return

    await msg.bot.send_message(partner["id"], msg.text)

