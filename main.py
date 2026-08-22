import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BotCommand, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import db
from handlers import format_user, router


async def nightly_matching(bot: Bot) -> None:
    today = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")
    pairs, leftover = db.do_matching(today)

    for u1, u2 in pairs:
        info1 = db.get_user(u1)
        info2 = db.get_user(u2)
        try:
            await bot.send_message(u1, build_match_message(info2))
        except Exception as e:
            logging.warning("Не удалось уведомить %s: %s", u1, e)
        try:
            await bot.send_message(u2, build_match_message(info1))
        except Exception as e:
            logging.warning("Не удалось уведомить %s: %s", u2, e)

    if leftover:
        try:
            await bot.send_message(leftover, "😔 Сегодня тебе не хватило пары. Новый собеседник появится завтра в 00:00.")
        except Exception as e:
            logging.warning("Не удалось уведомить %s: %s", leftover, e)


def build_match_message(partner: dict) -> str:
    topics = "\n".join(f"• {t}" for t in config.TOPICS)
    return (
        f"🎉 Тебя свели с новым собеседником!\n\n"
        f"{format_user(partner)}\n\n"
        f"Можете приступать к общению.\n\n"
        f"💡 О чём можно поговорить:\n{topics}"
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    db.init_db()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    @dp.message(Command("matchnow"))
    async def cmd_matchnow(msg: Message) -> None:
        if msg.from_user.id not in config.ADMIN_IDS:
            await msg.answer("Нет доступа.")
            return
        await nightly_matching(bot)
        await msg.answer("Подбор выполнен.")

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

