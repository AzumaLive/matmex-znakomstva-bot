import asyncio
import logging
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import db
from handlers import PARTNER_LEFT_MESSAGE, format_user, router

BAN_MESSAGE = "Вы забанены. Если тебе кажется, что произошла ошибка — пиши @forev4r_young1."


class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            user = db.get_user(event.from_user.id)
            if user and user.get("banned"):
                await event.answer(BAN_MESSAGE)
                return
        return await handler(event, data)


async def nightly_matching(bot: Bot) -> None:
    if db.get_setting("matching_enabled", "1") != "1":
        logging.info("Автоподбор выключен, пропускаю.")
        return
    today = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")
    pairs, leftover = db.do_matching(today)

    for u1, u2 in pairs:
        info1 = db.get_user(u1)
        info2 = db.get_user(u2)
        forbidden = set(db.get_last_topics(u1)) | set(db.get_last_topics(u2))
        available = [t for t in config.TOPICS if t not in forbidden]
        if len(available) >= 3:
            topics = random.sample(available, 3)
        else:
            topics = random.sample(config.TOPICS, 3)
        db.set_last_topics(u1, topics)
        db.set_last_topics(u2, topics)
        try:
            await bot.send_message(u1, build_match_message(info2, topics))
        except Exception as e:
            logging.warning("Не удалось уведомить %s: %s", u1, e)
        try:
            await bot.send_message(u2, build_match_message(info1, topics))
        except Exception as e:
            logging.warning("Не удалось уведомить %s: %s", u2, e)

    if leftover:
        try:
            await bot.send_message(leftover, "😔 Сегодня тебе не хватило пары. Новый собеседник появится завтра в 00:00.")
        except Exception as e:
            logging.warning("Не удалось уведомить %s: %s", leftover, e)


def build_match_message(partner: dict, topics: list) -> str:
    topics_str = "\n".join(f"• {t}" for t in topics)
    return (
        f"🎉 Тебя свели с новым собеседником!\n\n"
        f"{format_user(partner)}\n\n"
        f"Можете приступать к общению.\n\n"
        f"💡 О чём можно поговорить:\n{topics_str}"
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp.message.middleware(BanMiddleware())

    @dp.message(Command("matchnow"))
    async def cmd_matchnow(msg: Message) -> None:
        if msg.from_user.id not in config.ADMIN_IDS:
            await msg.answer("Нет доступа.")
            return
        await nightly_matching(bot)
        await msg.answer("Подбор выполнен.")

    @dp.message(Command("users"))
    async def cmd_users(msg: Message) -> None:
        if msg.from_user.id not in config.ADMIN_IDS:
            await msg.answer("Нет доступа.")
            return
        users = db.get_all_users()
        if not users:
            await msg.answer("Пользователей нет.")
            return
        lines = []
        for u in users:
            if u.get("banned"):
                status = "забанена"
            elif u.get("active", 1):
                status = "активна"
            else:
                status = "выключена"
            group = f", группа {u['group_num']}" if u.get("group_num") else ""
            lines.append(
                f"• {u['first_name']} {u['last_name']} — {u['role']}{group} "
                f"[id {u['id']}], анкета {status}"
            )
        await msg.answer(
            f"👥 Пользователей: {len(users)}\n\n" + "\n".join(lines)
        )

    @dp.message(Command("matching"))
    async def cmd_matching(msg: Message) -> None:
        if msg.from_user.id not in config.ADMIN_IDS:
            await msg.answer("Нет доступа.")
            return
        parts = msg.text.split()
        if len(parts) > 1:
            arg = parts[1].lower()
            if arg == "on":
                db.set_setting("matching_enabled", "1")
                await msg.answer("Автоподбор в 00:00 включён.")
            elif arg == "off":
                db.set_setting("matching_enabled", "0")
                await msg.answer("Автоподбор в 00:00 выключен.")
            else:
                await msg.answer("Использование: /matching on|off")
        else:
            state = db.get_setting("matching_enabled", "1")
            await msg.answer(
                "Автоподбор в 00:00: " + ("включён" if state == "1" else "выключен")
            )

    @dp.message(Command("ban"))
    async def cmd_ban(msg: Message) -> None:
        if msg.from_user.id not in config.ADMIN_IDS:
            await msg.answer("Нет доступа.")
            return
        parts = msg.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await msg.answer("Использование: /ban <id>")
            return
        target = int(parts[1])
        user = db.get_user(target)
        if not user:
            await msg.answer("Пользователь с таким id не найден.")
            return
        db.set_banned(target, True)
        db.set_active(target, False)
        today = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")
        partner = db.get_active_partner(target, today)
        if partner:
            db.end_pair(target, today)
            await bot.send_message(partner["id"], PARTNER_LEFT_MESSAGE)
        try:
            await bot.send_message(target, BAN_MESSAGE)
        except Exception as e:
            logging.warning("Не удалось уведомить забаненного %s: %s", target, e)
        await msg.answer(f"🚫 {user['first_name']} {user['last_name']} (id {target}) забанен.")

    @dp.message(Command("unban"))
    async def cmd_unban(msg: Message) -> None:
        if msg.from_user.id not in config.ADMIN_IDS:
            await msg.answer("Нет доступа.")
            return
        parts = msg.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await msg.answer("Использование: /unban <id>")
            return
        target = int(parts[1])
        user = db.get_user(target)
        if not user:
            await msg.answer("Пользователь с таким id не найден.")
            return
        db.set_banned(target, False)
        await msg.answer(f"✅ {user['first_name']} {user['last_name']} (id {target}) разбанен.")

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Меню и моя анкета"),
            BotCommand(command="partner", description="Информация о собеседнике"),
            BotCommand(command="end", description="Завершить общение"),
            BotCommand(command="register", description="Изменить анкету"),
            BotCommand(command="cancel", description="Отменить регистрацию"),
        ]
    )

    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(
        nightly_matching,
        CronTrigger(hour=config.PAIR_START_HOUR, minute=config.PAIR_START_MINUTE),
        args=[bot],
    )
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())

