"""
Патрик Stars | Звёзды и подарки бесплатно
Telegram Bot on aiogram 3.x + SQLite
Admin ID: 880628963
"""

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ─────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ — читаем из env (Render) или используем дефолт
# ─────────────────────────────────────────────────────────────
import os

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "ИМЯ_БОТА")
ADMIN_ID     = 880628963
DB_PATH      = "patrick_stars.db"

# Вебхук-конфигурация (читается ДО создания Bot — чтобы токен уже был из env)
WEBHOOK_HOST    = os.environ.get("WEBHOOK_HOST", "")
WEBHOOK_PATH    = "/webhook/patrickstars"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL     = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
USE_WEBHOOK     = bool(WEBHOOK_HOST)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ─────────────────────────────────────────────────────────────
# БАЗА ДАННЫХ
# ─────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    """Контекстный менеджер для работы с SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Создаёт таблицы и наполняет тестовыми заданиями."""
    with get_db() as conn:
        cur = conn.cursor()

        # Таблица пользователей
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT,
                first_name      TEXT,
                balance         REAL    DEFAULT 0.0,
                referrer_id     INTEGER DEFAULT NULL,
                invited_count   INTEGER DEFAULT 0,
                activated_count INTEGER DEFAULT 0,
                daily_claimed_at TEXT   DEFAULT NULL
            )
        """)

        # Таблица заданий
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT,
                reward      REAL,
                link        TEXT,
                channel_id  TEXT
            )
        """)

        # Лог выполненных заданий
        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_tasks (
                user_id INTEGER,
                task_id INTEGER,
                PRIMARY KEY (user_id, task_id)
            )
        """)

        # Промокоды
        cur.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code        TEXT PRIMARY KEY,
                reward      REAL,
                max_uses    INTEGER DEFAULT 1,
                used_count  INTEGER DEFAULT 0
            )
        """)

        # Использованные промокоды
        cur.execute("""
            CREATE TABLE IF NOT EXISTS used_promos (
                user_id INTEGER,
                code    TEXT,
                PRIMARY KEY (user_id, code)
            )
        """)

        # Тестовые задания (если таблица пустая)
        cur.execute("SELECT COUNT(*) as cnt FROM tasks")
        if cur.fetchone()["cnt"] == 0:
            cur.executemany(
                "INSERT INTO tasks (text, reward, link, channel_id) VALUES (?,?,?,?)",
                [
                    ("Подпишись на канал Патрик Stars", 0.4, "https://t.me/patrickstarsfarm", "-100123456789"),
                    ("Подпишись на канал с отзывами", 0.3, "https://t.me/patrickstars_reviews", "-100987654321"),
                    ("Подпишись на наш новостной канал", 0.5, "https://t.me/durov", "-100111222333"),
                ],
            )

# ─────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str, first_name: str, referrer_id: int = None):
    """Возвращает пользователя. Если нового — создаёт и обрабатывает реферала."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()

        if row:
            # Обновляем имя/юзернейм при каждом входе
            cur.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username, first_name, user_id),
            )
            return dict(row), False  # (user, is_new)

        # Новый пользователь
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id) VALUES (?,?,?,?)",
            (user_id, username, first_name, referrer_id),
        )

        # Начисляем рефереру
        if referrer_id and referrer_id != user_id:
            cur.execute(
                """UPDATE users
                   SET balance = balance + 3.0,
                       invited_count = invited_count + 1,
                       activated_count = activated_count + 1
                   WHERE user_id=?""",
                (referrer_id,),
            )

        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(cur.fetchone()), True  # (user, is_new)


def get_user(user_id: int):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def add_balance(user_id: int, amount: float):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (amount, user_id),
        )


def get_next_task(user_id: int):
    """Возвращает первое невыполненное задание."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM tasks
               WHERE id NOT IN (
                   SELECT task_id FROM completed_tasks WHERE user_id=?
               )
               LIMIT 1""",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_next_task_after(user_id: int, current_task_id: int):
    """Возвращает следующее невыполненное задание после пропуска."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM tasks
               WHERE id NOT IN (
                   SELECT task_id FROM completed_tasks WHERE user_id=?
               )
               AND id != ?
               LIMIT 1""",
            (user_id, current_task_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def complete_task(user_id: int, task_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO completed_tasks (user_id, task_id) VALUES (?,?)",
            (user_id, task_id),
        )


def can_claim_daily(user_id: int) -> bool:
    user = get_user(user_id)
    if not user or not user["daily_claimed_at"]:
        return True
    return user["daily_claimed_at"] != str(date.today())


def claim_daily(user_id: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + 0.10, daily_claimed_at=? WHERE user_id=?",
            (str(date.today()), user_id),
        )


def get_top_users(limit: int = 10):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, first_name, activated_count FROM users ORDER BY activated_count DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_all_users():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        return [r["user_id"] for r in cur.fetchall()]


def get_stats():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM users")
        users = cur.fetchone()["cnt"]
        cur.execute("SELECT SUM(balance) as s FROM users")
        total_bal = cur.fetchone()["s"] or 0
        cur.execute("SELECT COUNT(*) as cnt FROM completed_tasks")
        tasks_done = cur.fetchone()["cnt"]
        return users, total_bal, tasks_done


def get_all_tasks():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks")
        return [dict(r) for r in cur.fetchall()]


def delete_task(task_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.execute("DELETE FROM completed_tasks WHERE task_id=?", (task_id,))


def add_task(text: str, reward: float, link: str, channel_id: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (text, reward, link, channel_id) VALUES (?,?,?,?)",
            (text, reward, link, channel_id),
        )


def add_promo(code: str, reward: float, max_uses: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO promo_codes (code, reward, max_uses, used_count) VALUES (?,?,?,0)",
            (code, reward, max_uses),
        )


def use_promo(user_id: int, code: str):
    """Возвращает (success, reward, reason)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM promo_codes WHERE code=?", (code,))
        promo = cur.fetchone()
        if not promo:
            return False, 0, "Промокод не найден!"
        if promo["used_count"] >= promo["max_uses"]:
            return False, 0, "Промокод уже исчерпан!"
        cur.execute("SELECT 1 FROM used_promos WHERE user_id=? AND code=?", (user_id, code))
        if cur.fetchone():
            return False, 0, "Ты уже использовал этот промокод!"
        conn.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code=?", (code,))
        conn.execute("INSERT INTO used_promos (user_id, code) VALUES (?,?)", (user_id, code))
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (promo["reward"], user_id))
        return True, promo["reward"], ""


# ─────────────────────────────────────────────────────────────
# КЛАВИАТУРЫ
# ─────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚔️ PvP игры"),       KeyboardButton(text="✨ Кликер")],
            [KeyboardButton(text="⭐️ Заработать звезды")],
            [KeyboardButton(text="👤 Профиль"),         KeyboardButton(text="💰 Вывод звезд")],
            [KeyboardButton(text="📝 Задания"),          KeyboardButton(text="📚 Инструкция")],
            [KeyboardButton(text="👑 Топ"),             KeyboardButton(text="💼 NFT кейсы")],
            [KeyboardButton(text="🛒 Магазин звёзд"),   KeyboardButton(text="💬 Отзывы")],
        ],
        resize_keyboard=True,
    )


def profile_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎫 Промокод",    callback_data="promo"),
            InlineKeyboardButton(text="🎁 Ежедневка",  callback_data="daily"),
        ],
        [InlineKeyboardButton(text="🌕 +2⭐️ за старых друзей", callback_data="old_friends")],
        [InlineKeyboardButton(text="💫 Перевести ⭐️ другу",    callback_data="transfer")],
        [InlineKeyboardButton(text="⬅️ В главное меню",         callback_data="main_menu")],
    ])


def withdrawal_inline_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    gifts = [
        ("15 ⭐️ (🧝)", 15), ("15 ⭐️ (💝)", 15),
        ("25 ⭐️ (🌹)", 25), ("25 ⭐️ (🎁)", 25),
        ("50 ⭐️ (🎷)", 50), ("50 ⭐️ (🎪)", 50),
        ("50 ⭐️ (🚀)", 50), ("50 ⭐️ (👑)", 50),
    ]
    for label, cost in gifts:
        builder.button(text=label, callback_data=f"withdraw_{cost}")
    builder.adjust(2)
    builder.button(text="Telegram Premium — 3 мес. (900 ⭐️)",  callback_data="withdraw_900")
    builder.button(text="Telegram Premium — 6 мес. (1200 ⭐️)", callback_data="withdraw_1200")
    builder.button(text="⬅️ В главное меню", callback_data="main_menu")
    builder.adjust(2, 2, 2, 2, 1, 1, 1)
    return builder.as_markup()


def task_inline_kb(task: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Подписаться", url=task["link"])],
        [InlineKeyboardButton(text="✅ Подтвердить подписку", callback_data=f"check_{task['id']}")],
        [InlineKeyboardButton(text="Пропустить ➡️",           callback_data=f"skip_{task['id']}")],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",          callback_data="adm_stats")],
        [InlineKeyboardButton(text="📝 Список заданий",      callback_data="adm_tasks")],
        [InlineKeyboardButton(text="➕ Добавить задание",     callback_data="adm_add_task")],
        [InlineKeyboardButton(text="🎫 Создать промокод",    callback_data="adm_add_promo")],
        [InlineKeyboardButton(text="📢 Рассылка",            callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💰 Начислить баланс",    callback_data="adm_give_balance")],
    ])

# ─────────────────────────────────────────────────────────────
# FSM-СОСТОЯНИЯ (простая реализация через dict)
# ─────────────────────────────────────────────────────────────
# state: {user_id: {"state": str, "data": dict}}
user_states: dict = {}

def set_state(user_id: int, state: str, data: dict = None):
    user_states[user_id] = {"state": state, "data": data or {}}

def get_state(user_id: int):
    return user_states.get(user_id, {})

def clear_state(user_id: int):
    user_states.pop(user_id, None)


# ─────────────────────────────────────────────────────────────
# /start ХЭНДЛЕР
# ─────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    referrer_id = None
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
        except ValueError:
            pass

    uid = message.from_user.id
    uname = message.from_user.username or "—"
    fname = message.from_user.first_name or "Друг"

    user, is_new = get_or_create_user(uid, uname, fname, referrer_id)

    # Уведомляем реферера о новом друге
    if is_new and referrer_id and referrer_id != uid:
        try:
            await bot.send_message(
                referrer_id,
                f"🎉 Ура! По твоей ссылке зарегистрировался новый друг!\n"
                f"💰 +3.0 ⭐️ зачислено на твой баланс!",
            )
        except Exception:
            pass

    welcome = (
        "🌟 Добро пожаловать в <b>Патрик Stars</b>!\n\n"
        "Получи свою личную ссылку — жми «⭐️ Заработать звезды»\n"
        "🔮 Приглашай друзей — <b>3 ⭐️ за каждого!</b>\n"
        "🎰 Играй в PvP — выигрывай ещё больше 🌟\n\n"
        "✅ <b>Дополнительно:</b>\n"
        "— Ежедневные награды и промокоды (Профиль)\n"
        "— Выполняй задания\n"
        "— Открывай NFT кейсы!\n"
        "— Участвуй в конкурсе на топ"
    )
    await message.answer(welcome, reply_markup=main_menu_kb(), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ — REPLY-КНОПКИ
# ─────────────────────────────────────────────────────────────

# ── 👤 Профиль ──────────────────────────────────────────────
@router.message(F.text == "👤 Профиль")
async def btn_profile(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала напиши /start!")
        return

    uname = user["username"] or "—"
    text = (
        "✨ <b>Профиль</b>\n\n"
        f"💬 Имя: {user['first_name']}\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Username: @{uname}\n\n"
        f"👥 Всего друзей: {user['invited_count']}\n"
        f"✅ Активировали бота: {user['activated_count']}\n"
        f"🔄 Повторные активации: 0\n"
        f"💰 Баланс: {user['balance']:.2f} ⭐️\n\n"
        "⁉️ <b>Как получить ежедневный бонус?</b>\n"
        "Поставь свою личную ссылку на бота в описание своего тг аккаунта, "
        "и получай за это +1 ⭐️ каждый день.\n\n"
        "⬇️ Используй кнопки ниже, чтобы ввести промокод, получить ежедневный бонус, "
        "отправить звезды на баланс друга, или получить повторную награду за уже приглашённых друзей"
    )
    await message.answer(text, reply_markup=profile_inline_kb(), parse_mode="HTML")


# ── ⭐️ Заработать звезды ────────────────────────────────────
@router.message(F.text == "⭐️ Заработать звезды")
async def btn_earn(message: Message):
    uid = message.from_user.id
    text = (
        f"🔗 <b>Твоя реферальная ссылка для приглашения друзей:</b>\n"
        f"https://t.me/{BOT_USERNAME}?start={uid}\n\n"
        "За каждого активного друга ты получишь <b>3 ⭐️</b>!"
    )
    await message.answer(text, parse_mode="HTML")


# ── 📝 Задания ───────────────────────────────────────────────
@router.message(F.text == "📝 Задания")
async def btn_tasks(message: Message):
    uid = message.from_user.id
    task = get_next_task(uid)
    if not task:
        await message.answer("✨ На данный момент доступных заданий нет. Загляни позже!")
        return
    await send_task(message, task)


async def send_task(message: Message, task: dict):
    text = (
        "✨ <b>Новое задание!</b> ✨\n\n"
        f"• {task['text']}\n"
        f"Награда: <b>{task['reward']} ⭐️</b>\n\n"
        "⚠️ Чтобы получить награду полностью, подпишись и НЕ отписывайся "
        "от канала/бота в течение 7-ми дней"
    )
    await message.answer(text, reply_markup=task_inline_kb(task), parse_mode="HTML")


# ── 💰 Вывод звезд ───────────────────────────────────────────
@router.message(F.text == "💰 Вывод звезд")
async def btn_withdrawal(message: Message):
    await message.answer(
        "💰 <b>Вывод звёзд</b>\n\nВыбери подарок для вывода:",
        reply_markup=withdrawal_inline_kb(),
        parse_mode="HTML",
    )


# ── 👑 Топ ───────────────────────────────────────────────────
@router.message(F.text == "👑 Топ")
async def btn_top(message: Message):
    top = get_top_users(10)
    lines = ["🏆 <b>Топ 10 за день:</b>\n"]
    medals = ["🥇", "🥈", "🥉"] + ["4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    for i, u in enumerate(top):
        uname = f"@{u['username']}" if u["username"] and u["username"] != "—" else u["first_name"]
        lines.append(f"{medals[i]} {uname} — {u['activated_count']} друзей")
    lines.append("\n🎁 Попади в топ и получи приз в конце дня!")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ── 📚 Инструкция ────────────────────────────────────────────
@router.message(F.text == "📚 Инструкция")
async def btn_instruction(message: Message):
    text = (
        "📌 <b>Как заработать до 1000 звёзд в день?</b>\n\n"
        "1. Скопируй ссылку в разделе «Заработать».\n"
        "2. Сними видео в TikTok/Shorts.\n"
        "3. Вставь ссылку в шапку профиля!"
    )
    await message.answer(text, parse_mode="HTML")


# ── ⚔️ PvP игры / ✨ Кликер ─────────────────────────────────
@router.message(F.text.in_({"⚔️ PvP игры", "✨ Кликер"}))
async def btn_pvp(message: Message):
    await message.answer(
        "🎮 Раздел находится в разработке. Скоро здесь будут мини-игры на звёзды!"
    )


# ── 💼 NFT кейсы ────────────────────────────────────────────
@router.message(F.text == "💼 NFT кейсы")
async def btn_nft(message: Message):
    await message.answer(
        "💼 Открытие NFT кейсов станет доступно в следующем обновлении!"
    )


# ── 🛒 Магазин звёзд / 💬 Отзывы ────────────────────────────
@router.message(F.text.in_({"🛒 Магазин звёзд", "💬 Отзывы"}))
async def btn_shop(message: Message):
    await message.answer(
        "⭐️ Наш официальный шоп: @patrickstarsfarm\n"
        "💬 Отзывы покупателей: @patrickstars_reviews"
    )


# ─────────────────────────────────────────────────────────────
# INLINE CALLBACKS
# ─────────────────────────────────────────────────────────────

# ── 🎁 Ежедневный бонус ─────────────────────────────────────
@router.callback_query(F.data == "daily")
async def cb_daily(callback: CallbackQuery):
    uid = callback.from_user.id
    if can_claim_daily(uid):
        claim_daily(uid)
        await callback.answer(
            "Патрик Stars | Звёзды и подарки бесплатно\n\n✅ Ты получил(а) 0.10 ⭐️",
            show_alert=True,
        )
    else:
        await callback.answer("Вы уже забирали бонус сегодня!", show_alert=True)


# ── 🎫 Промокод ─────────────────────────────────────────────
@router.callback_query(F.data == "promo")
async def cb_promo(callback: CallbackQuery):
    set_state(callback.from_user.id, "wait_promo")
    await callback.message.answer("🎫 Введи промокод:")
    await callback.answer()


# ── 🌕 +2⭐️ за старых друзей ─────────────────────────────────
@router.callback_query(F.data == "old_friends")
async def cb_old_friends(callback: CallbackQuery):
    await callback.answer(
        "Патрик Stars | Звёзды и подарки бесплатно\n\n"
        "🌕 Функция временно недоступна. Скоро запустим!",
        show_alert=True,
    )


# ── 💫 Перевести другу ──────────────────────────────────────
@router.callback_query(F.data == "transfer")
async def cb_transfer(callback: CallbackQuery):
    set_state(callback.from_user.id, "wait_transfer_id")
    await callback.message.answer(
        "💫 Введи ID пользователя, которому хочешь перевести ⭐️\n"
        "(его ID можно узнать через /start):"
    )
    await callback.answer()


# ── ⬅️ В главное меню ───────────────────────────────────────
@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu_kb())
    await callback.answer()


# ── 💰 Вывод ────────────────────────────────────────────────
@router.callback_query(F.data.startswith("withdraw_"))
async def cb_withdraw(callback: CallbackQuery):
    cost = int(callback.data.split("_")[1])
    user = get_user(callback.from_user.id)
    if not user or user["balance"] < cost:
        await callback.answer(
            "Патрик Stars | Звёзды и подарки бесплатно\n\n❌ Недостаточно звёзд для вывода!",
            show_alert=True,
        )
        return
    await callback.answer(
        f"✅ Заявка на вывод {cost} ⭐️ принята! Ожидай обработки.",
        show_alert=True,
    )
    # Уведомляем админа
    uname = callback.from_user.username or "—"
    await bot.send_message(
        ADMIN_ID,
        f"📤 <b>Запрос на вывод!</b>\n"
        f"👤 @{uname} (ID: {callback.from_user.id})\n"
        f"💰 Сумма: {cost} ⭐️\n"
        f"Баланс пользователя: {user['balance']:.2f} ⭐️",
        parse_mode="HTML",
    )


# ── 📝 Проверка подписки на задание ─────────────────────────
@router.callback_query(F.data.startswith("check_"))
async def cb_check_task(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    uid = callback.from_user.id

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = cur.fetchone()

    if not task:
        await callback.answer("Задание не найдено!", show_alert=True)
        return

    task = dict(task)
    try:
        member = await bot.get_chat_member(chat_id=task["channel_id"], user_id=uid)
        is_member = member.status not in (
            ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.BANNED
        )
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки: {e}")
        await callback.answer(
            "❌ Не удалось проверить подписку. Убедись, что бот — администратор канала.",
            show_alert=True,
        )
        return

    if is_member:
        complete_task(uid, task_id)
        add_balance(uid, task["reward"])
        await callback.answer(
            f"✅ Задание выполнено! +{task['reward']} ⭐️",
            show_alert=True,
        )
        # Показываем следующее задание
        next_task = get_next_task(uid)
        if next_task:
            await send_task(callback.message, next_task)
        else:
            await callback.message.answer("✨ Ты выполнил все доступные задания! Загляни позже.")
    else:
        await callback.answer("❌ Вы не подписались на канал!", show_alert=True)


# ── Пропустить задание ───────────────────────────────────────
@router.callback_query(F.data.startswith("skip_"))
async def cb_skip_task(callback: CallbackQuery):
    current_id = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    task = get_next_task_after(uid, current_id)
    if task:
        await send_task(callback.message, task)
    else:
        await callback.message.answer("✨ Больше нет доступных заданий. Загляни позже!")
    await callback.answer()


# ─────────────────────────────────────────────────────────────
# FSM — ОБРАБОТКА ТЕКСТОВЫХ СОСТОЯНИЙ
# ─────────────────────────────────────────────────────────────

@router.message()
async def handle_states(message: Message):
    uid = message.from_user.id
    state = get_state(uid)

    # ── Промокод ──────────────────────────────────────────────
    if state.get("state") == "wait_promo":
        clear_state(uid)
        code = message.text.strip()
        ok, reward, err = use_promo(uid, code)
        if ok:
            await message.answer(f"🎉 Промокод активирован! +{reward} ⭐️ на баланс!")
        else:
            await message.answer(f"❌ {err}")
        return

    # ── Перевод: ожидаем ID ──────────────────────────────────
    if state.get("state") == "wait_transfer_id":
        try:
            target_id = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверный формат ID. Попробуй ещё раз.")
            return
        set_state(uid, "wait_transfer_amount", {"target_id": target_id})
        await message.answer("💫 Введи количество ⭐️ для перевода:")
        return

    # ── Перевод: ожидаем сумму ───────────────────────────────
    if state.get("state") == "wait_transfer_amount":
        try:
            amount = float(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверная сумма. Введи число.")
            return
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля.")
            return
        user = get_user(uid)
        if not user or user["balance"] < amount:
            await message.answer("❌ Недостаточно звёзд!")
            clear_state(uid)
            return
        target_id = state["data"]["target_id"]
        target = get_user(target_id)
        if not target:
            await message.answer("❌ Пользователь с таким ID не найден.")
            clear_state(uid)
            return
        # Выполняем перевод
        with get_db() as conn:
            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, uid))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_id))
        clear_state(uid)
        await message.answer(f"✅ Переведено {amount} ⭐️ пользователю ID {target_id}!")
        try:
            await bot.send_message(
                target_id,
                f"💫 Тебе перевели {amount} ⭐️ от пользователя @{message.from_user.username or uid}!"
            )
        except Exception:
            pass
        return

    # ── Состояния админа ─────────────────────────────────────

    # Рассылка
    if state.get("state") == "adm_broadcast" and uid == ADMIN_ID:
        clear_state(uid)
        text = message.text
        all_users = get_all_users()
        sent = 0
        for target in all_users:
            try:
                await bot.send_message(target, text, parse_mode="HTML")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        await message.answer(f"✅ Рассылка завершена. Отправлено: {sent}/{len(all_users)}")
        return

    # Добавить задание — шаг 1: текст
    if state.get("state") == "adm_task_text" and uid == ADMIN_ID:
        set_state(uid, "adm_task_reward", {"text": message.text})
        await message.answer("Введи награду (число, например 0.5):")
        return

    # Добавить задание — шаг 2: награда
    if state.get("state") == "adm_task_reward" and uid == ADMIN_ID:
        try:
            reward = float(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверная награда. Введи число.")
            return
        data = state["data"]
        data["reward"] = reward
        set_state(uid, "adm_task_link", data)
        await message.answer("Введи ссылку на канал:")
        return

    # Добавить задание — шаг 3: ссылка
    if state.get("state") == "adm_task_link" and uid == ADMIN_ID:
        data = state["data"]
        data["link"] = message.text.strip()
        set_state(uid, "adm_task_channel_id", data)
        await message.answer("Введи ID канала (например -100123456789):")
        return

    # Добавить задание — шаг 4: channel_id
    if state.get("state") == "adm_task_channel_id" and uid == ADMIN_ID:
        data = state["data"]
        add_task(data["text"], data["reward"], data["link"], message.text.strip())
        clear_state(uid)
        await message.answer("✅ Задание добавлено!")
        return

    # Добавить промокод — шаг 1: код
    if state.get("state") == "adm_promo_code" and uid == ADMIN_ID:
        set_state(uid, "adm_promo_reward", {"code": message.text.strip()})
        await message.answer("Введи награду за промокод (число):")
        return

    # Добавить промокод — шаг 2: награда
    if state.get("state") == "adm_promo_reward" and uid == ADMIN_ID:
        try:
            reward = float(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверная награда.")
            return
        data = state["data"]
        data["reward"] = reward
        set_state(uid, "adm_promo_uses", data)
        await message.answer("Введи максимальное кол-во использований:")
        return

    # Добавить промокод — шаг 3: кол-во использований
    if state.get("state") == "adm_promo_uses" and uid == ADMIN_ID:
        try:
            uses = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверное число.")
            return
        data = state["data"]
        add_promo(data["code"], data["reward"], uses)
        clear_state(uid)
        await message.answer(f"✅ Промокод <code>{data['code']}</code> создан! Награда: {data['reward']} ⭐️, использований: {uses}", parse_mode="HTML")
        return

    # Начислить баланс — шаг 1: ID
    if state.get("state") == "adm_give_id" and uid == ADMIN_ID:
        try:
            target_id = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверный ID.")
            return
        set_state(uid, "adm_give_amount", {"target_id": target_id})
        await message.answer("Введи сумму для начисления:")
        return

    # Начислить баланс — шаг 2: сумма
    if state.get("state") == "adm_give_amount" and uid == ADMIN_ID:
        try:
            amount = float(message.text.strip())
        except ValueError:
            await message.answer("❌ Неверная сумма.")
            return
        target_id = state["data"]["target_id"]
        add_balance(target_id, amount)
        clear_state(uid)
        await message.answer(f"✅ Начислено {amount} ⭐️ пользователю {target_id}!")
        try:
            await bot.send_message(target_id, f"🎁 Администратор начислил тебе {amount} ⭐️!")
        except Exception:
            pass
        return


# ─────────────────────────────────────────────────────────────
# АДМИН-ПАНЕЛЬ
# ─────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👑 <b>Панель администратора</b>",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML",
    )


# ── Статистика ───────────────────────────────────────────────
@router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    users, total_bal, tasks_done = get_stats()
    await callback.message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {users}\n"
        f"💰 Суммарный баланс: {total_bal:.2f} ⭐️\n"
        f"✅ Заданий выполнено: {tasks_done}",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Список заданий ───────────────────────────────────────────
@router.callback_query(F.data == "adm_tasks")
async def cb_adm_tasks(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    tasks = get_all_tasks()
    if not tasks:
        await callback.message.answer("Заданий нет.")
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for t in tasks:
        builder.button(
            text=f"🗑 #{t['id']} {t['text'][:25]}",
            callback_data=f"adm_del_task_{t['id']}",
        )
    builder.adjust(1)
    lines = [f"#{t['id']} | {t['text']} | {t['reward']} ⭐️" for t in tasks]
    await callback.message.answer(
        "📝 <b>Текущие задания:</b>\n\n" + "\n".join(lines) + "\n\nНажми для удаления:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_del_task_"))
async def cb_adm_del_task(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    task_id = int(callback.data.split("_")[-1])
    delete_task(task_id)
    await callback.answer(f"✅ Задание #{task_id} удалено!", show_alert=True)
    await callback.message.delete()


# ── Добавить задание ─────────────────────────────────────────
@router.callback_query(F.data == "adm_add_task")
async def cb_adm_add_task(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    set_state(callback.from_user.id, "adm_task_text")
    await callback.message.answer("✏️ Введи название задания:")
    await callback.answer()


# ── Создать промокод ─────────────────────────────────────────
@router.callback_query(F.data == "adm_add_promo")
async def cb_adm_add_promo(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    set_state(callback.from_user.id, "adm_promo_code")
    await callback.message.answer("🎫 Введи код промокода:")
    await callback.answer()


# ── Рассылка ─────────────────────────────────────────────────
@router.callback_query(F.data == "adm_broadcast")
async def cb_adm_broadcast(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    set_state(callback.from_user.id, "adm_broadcast")
    await callback.message.answer(
        "📢 Введи текст рассылки (поддерживается HTML):"
    )
    await callback.answer()


# ── Начислить баланс ─────────────────────────────────────────
@router.callback_query(F.data == "adm_give_balance")
async def cb_adm_give_balance(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    set_state(callback.from_user.id, "adm_give_id")
    await callback.message.answer("💰 Введи Telegram ID пользователя:")
    await callback.answer()





# ─────────────────────────────────────────────────────────────
# ЗАПУСК — POLLING (локально / без WEBHOOK_HOST)
# ─────────────────────────────────────────────────────────────

async def run_polling():
    init_db()
    logger.info("✅ БД инициализирована")
    logger.info("🚀 Режим: POLLING")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


# ─────────────────────────────────────────────────────────────
# ЗАПУСК — WEBHOOK (Render и любой https-сервер)
# ─────────────────────────────────────────────────────────────

async def run_webhook():
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    init_db()
    logger.info("✅ БД инициализирована")
    logger.info(f"🚀 Режим: WEBHOOK → {WEBHOOK_URL}")
    logger.info(f"🌐 Слушаю {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")

    # Регистрируем вебхук в Telegram
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

    # Создаём aiohttp-приложение
    app = web.Application()

    # Health-check — Render пингует GET / чтобы убедиться что сервис живой
    async def health(request):
        return web.Response(text="OK")
    app.router.add_get("/", health)

    # Обработчик апдейтов от Telegram
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
    await site.start()

    logger.info("✅ Сервер запущен, ждём апдейты...")

    # Держим процесс живым
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.delete_webhook()


# ─────────────────────────────────────────────────────────────
# ТОЧКА ВХОДА
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if USE_WEBHOOK:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())
