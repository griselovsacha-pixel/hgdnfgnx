import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart,Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Токен твоего бота
TOKEN = "8989832302:AAHWAAbab8xTqHZsqvwwH2MCoOQl1RsrCPE"
dp = Dispatcher()

# Обработчик команды /start
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Привет! Бот успешно запущен на Render 🚀")
# Обработчик команды /hi
@dp.message(Command("hi"))
async def command_start_handler(message: Message) -> None:
 await message.answer(f"это команда привет 🚀")
# Настройка вебхука при старте сервера
async def on_startup(bot: Bot) -> None:
    BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
    WEBHOOK_PATH = f"/webhook/{TOKEN}"
    await bot.set_webhook(url=f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}")

def main():
    bot = Bot(token=TOKEN)
    app = web.Application()
    
    # Связываем aiogram с веб-сервером aiohttp
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=f"/webhook/{TOKEN}")
    
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    
    # Render сам передает порт через переменную окружения PORT
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

if __name__ == "__main__":
    main()
