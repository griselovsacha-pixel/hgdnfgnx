import os
import sqlite3
import logging
import datetime
from typing import Optional, List, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ==========================================
# НАСТРОЙКИ БОТА (ОБЯЗАТЕЛЬНО ЗАПОЛНИ)
# ==========================================
BOT_TOKEN = "8989832302:AAHWAAbab8xTqHZsqvwwH2MCoOQl1RsrCPE"
BOT_USERNAME = "ИМЯ_ТВОЕГО_БОТА"  # Без знака @
DB_NAME = "patrick_stars.db"      # Если на Render подключен диск, укажи путь: "/data/patrick_stars.db"

# ==========================================
# КЛАСС ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ SQLite
# ==========================================
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance REAL DEFAULT 0.0,
                    referrer_id INTEGER DEFAULT NULL,
                    invited_count INTEGER DEFAULT 0,
                    activated_count INTEGER DEFAULT 0,
                    daily_claimed_at TEXT DEFAULT NULL
                )
            ''')
            conn.commit()

    def get_user(self, user_id: int) -> Optional[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()

    def add_user(self, user_id: int, username: str, first_name: str, referrer_id: Optional[int] = None) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if cursor.fetchone() is not None:
                return False  

            valid_referrer = None
            if referrer_id and referrer_id != user_id:
                cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (referrer_id,))
                if cursor.fetchone():
                    valid_referrer = referrer_id

            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, referrer_id)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, valid_referrer))

            if valid_referrer:
                cursor.execute('''
                    UPDATE users 
                    SET balance = balance + 3.0, 
                        invited_count = invited_count + 1, 
                        activated_count = activated_count + 1
                    WHERE user_id = ?
                ''', (valid_referrer,))
            
            conn.commit()
            return True

    def claim_daily(self, user_id: int) -> Tuple[bool, float]:
        now = datetime.datetime.now().date().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT daily_claimed_at FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0] == now:
                return False, 0.0  
            
            reward = 0.10
            cursor.execute('''
                UPDATE users 
                SET balance = balance + ?, daily_claimed_at = ? 
                WHERE user_id = ?
            ''', (reward, now, user_id))
            conn.commit()
            return True, reward

    def update_balance(self, user_id: int, amount: float):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
            conn.commit()

    def get_top_users(self, limit: int = 10) -> List[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, first_name, activated_count 
                FROM users 
                ORDER BY activated_count DESC, balance DESC 
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()

db = Database(DB_NAME)
dp = Dispatcher()

# ==========================================
# СБОРКА КЛАВИАТУР (KEYBOARDS)
# ==========================================
def get_main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="⚔️ PvP игры"), KeyboardButton(text="✨ Кликер"))
    builder.row(KeyboardButton(text="⭐️ Заработать звезды"))
    builder.row(KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💰 Вывод звезд"))
    builder.row(KeyboardButton(text="📝 Задания"), KeyboardButton(text="📚 Инструкция"))
    builder.row(KeyboardButton(text="👑 Топ"), KeyboardButton(text="💼 NFT кейсы"))
    builder.row(KeyboardButton(text="🛒 Магазин звёзд"), KeyboardButton(text="💬 Отзывы"))
    return builder.as_markup(resize_keyboard=True)

def get_profile_inline() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎫 Промокод", callback_data="prof_promo"),
                InlineKeyboardButton(text="🎁 Ежедневка", callback_data="prof_daily"))
    builder.row(InlineKeyboardButton(text="🌕 +2⭐️ за старых друзей", callback_data="prof_old_friends"))
    builder.row(InlineKeyboardButton(text="💫 Перевести ⭐️ другу", callback_data="prof_transfer"))
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="to_main"))
    return builder.as_markup()

# ==========================================
# ОБРАБОТЧИКИ ДЛЯ REPLY-КНОПОК
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)

    username = message.from_user.username or f"id{message.from_user.id}"
    first_name = message.from_user.first_name

    db.add_user(user_id=message.from_user.id, username=username, first_name=first_name, referrer_id=referrer_id)

    welcome_text = (
        "Получi свою личную ссылку — жми «⭐️ Заработать звезды»\n"
        "🔮 Приглашай друзей — 3 ⭐️ за каждого!\n"
        "🎰 Играй в PvP — выигрывай еще больше 🌟\n\n"
        "✅ Дополнительно:\n"
        "— Ежедневные награды и промокоды (Профиль)\n"
        "— Выполняй задания\n"
        "— Открывай NFT кейсы!\n"
        "— Участвуй в конкурсе на топ"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu())

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_data = db.get_user(message.from_user.id)
    if not user_data: return

    _, username, first_name, balance, _, invited_count, activated_count, _ = user_data

    profile_text = (
        f"✨ Профиль\n💬 Имя: {first_name}\n🆔 ID: {message.from_user.id}\n👤 Username: @{username}\n\n"
        f"👥 Всего друзей: {invited_count}\n✅ Активировали бота: {activated_count}\n🔄 Повторные активации: 0\n"
        f"💰 Баланс: {balance:.2f} ⭐️\n\n⁉️ Как получить ежедневный бонус?\n"
        f"Поставь свою личную ссылку на бота в описание своего тг аккаунта, и получай за это +1⭐️ каждый день.\n\n"
        f"⬇️ Используй кнопки ниже, чтобы ввести промокод, получить ежедневный бонус, "
        f"отправить звезды на баланс друга, или получить повторную награду за уже приглашенных друзей"
    )
    await message.answer(profile_text, reply_markup=get_profile_inline())

@dp.message(F.text == "⭐️ Заработать звезды")
async def earn_stars(message: Message):
    ref_link = f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}"
    await message.answer(f"Твоя личная реферальная ссылка:\n{ref_link}")

@dp.message(F.text == "💰 Вывод звезд")
async def withdraw_stars(message: Message):
    builder = InlineKeyboardBuilder()
    gifts = [
        ("15 ⭐️ (🧝)", 15), ("15 ⭐️ (💝)", 15), ("25 ⭐️ (🌹)", 25), ("25 ⭐️ (🎁)", 25),
        ("50 ⭐️ (🎷)", 50), ("50 ⭐️ (🎪)", 50), ("50 ⭐️ (🚀)", 50), ("50 ⭐️ (👑)", 50),
        ("50 ⭐️ (😎)", 50), ("50 ⭐️ (🍙)", 50), ("50 ⭐️ (🦁)", 50), ("50 ⭐️ (🍀)", 50),
        ("50 ⭐️ (🦅)", 50), ("100 ⭐️ (🏆)", 100), ("100 ⭐️ (💍)", 100), ("100 ⭐️ (💎)", 100),
        ("Telegram Premium — 3 мес. (900 ⭐️)", 900), ("Telegram Premium — 6 мес. (1200 ⭐️)", 1200)
    ]
    for text, cost in gifts:
        builder.add(InlineKeyboardButton(text=text, callback_data=f"withdraw_{cost}"))
    
    builder.adjust(2, 2, 2, 2, 2, 2, 1, 2, 1, 1, 1)
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="to_main"))
    await message.answer("Сетка доступных подарков для отправки другу или вывода:", reply_markup=builder.as_markup())

@dp.message(F.text == "📝 Задания")
async def show_tasks(message: Message):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔗 Подписаться", url="https://t.me/patrickstarsfarm"))
    builder.row(InlineKeyboardButton(text="✅ Подтвердить подписку", callback_data="task_confirm_0.4"))
    builder.row(InlineKeyboardButton(text="Пропустить ➡️", callback_data="to_main"))
    
    task_text = (
        "✨ Новое задание! ✨\n• Подпишись на канал\nНаграда: 0.4 ⭐️\n"
        "⚠️ Чтобы получить награду полностью, подпишись и НЕ отписывайся от канала/бота в течение 7-ми дней"
    )
    await message.answer(task_text, reply_markup=builder.as_markup())

@dp.message(F.text == "👑 Топ")
async def show_top(message: Message):
    top_users = db.get_top_users(10)
    text = "🏆 Топ 10 за день:\n"
    for idx, (username, first_name, count) in enumerate(top_users, start=1):
        display_name = f"@{username}" if username else first_name
        text += f"{idx}. {display_name} | Друзей: {count}\n"
        
    text += "\nПопади в топ и получи приз в конце дня:\n1-е место + 200 ⭐️\n2-е место + 100 ⭐️\n3-е место + 50 ⭐️\n...\n✨ Ты пока не в топе за этот день..."
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="to_main"))
    await message.answer(text, reply_markup=builder.as_markup())

@dp.message(F.text == "📚 Инструкция")
async def show_instruction(message: Message):
    inst_text = "📌 Как набрать много переходов по ссылке?\n• Отправь её друзьям в личные сообщения...\n• Способы, которыми можно заработать до 1000 звёзд в день:\n1 Первый способ: Заходим в TikTok или Лайк..."
    await message.answer(inst_text)

@dp.message(F.text == "🛒 Магазин звёзд")
async def show_shop(message: Message):
    await message.answer("⭐️ Покупай звезды у Патрика НАМНОГО дешевле чем в тг. Наш канал: @patrickstarsfarm, Поддержка: @patrickshop_support")

@dp.message(F.text.in_({"⚔️ PvP игры", "✨ Кликер", "💼 NFT кейсы", "💬 Отзывы"}))
async def process_stubs(message: Message):
    await message.answer(f"Раздел '{message.text}' находится в разработке!")

# ==========================================
# ОБРАБОТЧИКИ ДЛЯ INLINE-КНОПОК
# ==========================================
@dp.callback_query(F.data == "prof_daily")
async def process_daily(callback: CallbackQuery):
    success, reward = db.claim_daily(callback.from_user.id)
    if success:
        await callback.answer(f"Патрик Stars | Звёзды и подарки бесплатно \n\n ✅ Ты получил(а) {reward:.2f} ⭐️", show_alert=True)
        user_data = db.get_user(callback.from_user.id)
        if user_data:
            _, username, first_name, balance, _, invited_count, activated_count, _ = user_data
            profile_text = (
                f"✨ Профиль\n💬 Имя: {first_name}\n🆔 ID: {callback.from_user.id}\n👤 Username: @{username}\n\n"
                f"👥 Всего друзей: {invited_count}\n✅ Активировали бота: {activated_count}\n💰 Баланс: {balance:.2f} ⭐️\n\n⬇️ Используй кнопки ниже:"
            )
            await callback.message.edit_text(profile_text, reply_markup=get_profile_inline())
    else:
        await callback.message.answer("Вы уже забирали бонус")
        await callback.answer()

@dp.callback_query(F.data == "prof_promo")
async def process_promo(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🎫 Создать промокод", callback_data="stub_alert"))
    promo_text = "Для получения звезд на твой баланс введи промокод. Найти промокоды можно в канале и чате... Чтобы создать промокод, необходимо иметь 5 друзей, активировавших бота"
    await callback.message.answer(promo_text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("withdraw_"))
async def process_withdrawal(callback: CallbackQuery):
    cost = int(callback.data.split("_")[1])
    user_data = db.get_user(callback.from_user.id)
    if user_data and user_data[3] >= cost:
        db.update_balance(callback.from_user.id, -float(cost))
        await callback.answer("✅ Заявка на вывод отправлена администратору!", show_alert=True)
    else:
        await callback.answer("Патрик Stars | Звёзды и подарки бесплатно \n\n ❌ Недостаточно звезд для вывода!", show_alert=True)

@dp.callback_query(F.data == "task_confirm_0.4")
async def process_task_confirm(callback: CallbackQuery):
    db.update_balance(callback.from_user.id, 0.4)
    await callback.answer("✅ Баланс успешно увеличен на 0.4 ⭐️", show_alert=True)
    await callback.message.delete()

@dp.callback_query(F.data == "to_main")
async def process_back_to_main(callback: CallbackQuery):
    await callback.message.answer("Вы вернулись в главное меню", reply_markup=get_main_menu())
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data.in_({"stub_alert", "prof_old_friends", "prof_transfer"}))
async def process_stubs_alerts(callback: CallbackQuery):
    await callback.answer("Эта функция станет доступна в ближайшем обновлении!", show_alert=True)

# ==========================================
# ЗАПУСК СЕРВЕРА ДЛЯ RENDER (WEBHOOK)
# ==========================================
async def on_startup(bot: Bot) -> None:
    base_url = os.getenv("RENDER_EXTERNAL_URL")
    if base_url:
        webhook_url = f"{base_url}/webhook"
        await bot.set_webhook(url=webhook_url)
        logging.info(f"Установлен вебхук: {webhook_url}")
    else:
        logging.warning("RENDER_EXTERNAL_URL отсутствует. Бот запущен локально.")

def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    app = web.Application()
    
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path="/webhook")
    
    dp.startup.register(on_startup)
    setup_application(app, dp, bot=bot)
    
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
