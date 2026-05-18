"""
👑 LION STARS | Звёзды и подарки бесплатно
═══════════════════════════════════════════
aiogram 3.x + SQLite (постоянная БД в /data/lionstars.db)
Admin ID: 880628963
"""

import asyncio
import logging
import os
import random
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

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

# ══════════════════════════════════════════════════════════════
# ⚙️ КОНФИГУРАЦИЯ
# ══════════════════════════════════════════════════════════════

BOT_TOKEN    = os.environ.get("BOT_TOKEN",    "ВСТАВЬ_ТОКЕН")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "ИМЯ_БОТА")
ADMIN_ID     = 880628963

WEBHOOK_HOST    = os.environ.get("WEBHOOK_HOST", "")
WEBHOOK_PATH    = "/webhook/lionstars"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL     = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
USE_WEBHOOK     = bool(WEBHOOK_HOST)

# ══════════════════════════════════════════════════════════════
# 🎮 ИГРОВЫЕ КОНСТАНТЫ
# ══════════════════════════════════════════════════════════════

CLICKER_LEVELS = {
    1: {"per_tap": 0.01, "upgrade": 5.0,   "name": "🐾 Детёныш"},
    2: {"per_tap": 0.02, "upgrade": 15.0,  "name": "🦁 Лев"},
    3: {"per_tap": 0.05, "upgrade": 40.0,  "name": "👑 Принц"},
    4: {"per_tap": 0.10, "upgrade": 100.0, "name": "⚔️ Воин"},
    5: {"per_tap": 0.25, "upgrade": 250.0, "name": "🌟 Вождь"},
    6: {"per_tap": 0.50, "upgrade": 500.0, "name": "💎 Король"},
    7: {"per_tap": 1.00, "upgrade": None,  "name": "🔱 Император"},
}

DAILY_REWARDS = {1: 0.10, 2: 0.15, 3: 0.20, 4: 0.30, 5: 0.40, 6: 0.60, 7: 1.00}

SLOT_SYMBOLS = ["🦁", "👑", "⭐️", "💎", "🔱", "🌟"]
SLOT_PAYOUTS = {
    ("🔱", "🔱", "🔱"): 10.0,
    ("💎", "💎", "💎"): 7.0,
    ("👑", "👑", "👑"): 5.0,
    ("🦁", "🦁", "🦁"): 4.0,
    ("🌟", "🌟", "🌟"): 3.0,
    ("⭐️", "⭐️", "⭐️"): 2.0,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

bot    = Bot(token=BOT_TOKEN)
dp     = Dispatcher()
router = Router()
dp.include_router(router)

# ══════════════════════════════════════════════════════════════
# 💾 БАЗА ДАННЫХ — SQLite в /data/
# ══════════════════════════════════════════════════════════════

DB_PATH = "/data/lionstars.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn, conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as (conn, cur):
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          INTEGER PRIMARY KEY,
                username         TEXT    DEFAULT '',
                first_name       TEXT    DEFAULT '',
                balance          REAL    DEFAULT 0.0,
                referrer_id      INTEGER DEFAULT NULL,
                invited_count    INTEGER DEFAULT 0,
                activated_count  INTEGER DEFAULT 0,
                daily_claimed_at TEXT    DEFAULT NULL,
                daily_streak     INTEGER DEFAULT 0,
                clicker_level    INTEGER DEFAULT 1,
                total_taps       INTEGER DEFAULT 0,
                total_earned     REAL    DEFAULT 0.0,
                pvp_wins         INTEGER DEFAULT 0,
                pvp_losses       INTEGER DEFAULT 0,
                pvp_total_bet    REAL    DEFAULT 0.0,
                is_banned        INTEGER DEFAULT 0,
                joined_at        TEXT    DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT,
                reward     REAL,
                link       TEXT,
                channel_id TEXT,
                is_active  INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS completed_tasks (
                user_id INTEGER,
                task_id INTEGER,
                done_at TEXT,
                PRIMARY KEY (user_id, task_id)
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                code       TEXT PRIMARY KEY,
                reward     REAL,
                max_uses   INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS used_promos (
                user_id INTEGER,
                code    TEXT,
                PRIMARY KEY (user_id, code)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount  REAL,
                reason  TEXT,
                ts      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pvp_duels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id  INTEGER,
                bet         REAL,
                status      TEXT DEFAULT 'open',
                opponent_id INTEGER DEFAULT NULL,
                winner_id   INTEGER DEFAULT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT COUNT(*) FROM tasks")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO tasks(text,reward,link,channel_id) VALUES(?,?,?,?)",
                [
                    ("Подпишись на Lion Stars", 0.5, "https://t.me/patrickstarsfarm", "-100123456789"),
                    ("Подпишись на канал отзывов", 0.3, "https://t.me/patrickstars_reviews", "-100987654321"),
                    ("Подпишись на новостной канал", 0.4, "https://t.me/durov", "-100111222333"),
                ],
            )
    logger.info("✅ БД инициализирована (SQLite в /data/lionstars.db)")

# ══════════════════════════════════════════════════════════════
# 🛠 DB ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════════════

def dict_from_row(row):
    return dict(row) if row else None

def get_or_create_user(user_id, username, first_name, referrer_id=None):
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                        (username or "", first_name or "", user_id))
            return dict(row), False
        cur.execute("INSERT INTO users(user_id,username,first_name,referrer_id,joined_at) VALUES(?,?,?,?,?)",
                    (user_id, username or "", first_name or "", referrer_id, str(date.today())))
        if referrer_id and referrer_id != user_id:
            cur.execute("UPDATE users SET balance=balance+3.0, invited_count=invited_count+1, "
                        "activated_count=activated_count+1, total_earned=total_earned+3.0 WHERE user_id=?",
                        (referrer_id,))
            cur.execute("INSERT INTO transactions(user_id,amount,reason) VALUES(?,?,?)",
                        (referrer_id, 3.0, f"👥 Реферал #{user_id}"))
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(cur.fetchone()), True

def get_user(user_id):
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict_from_row(cur.fetchone())

def add_balance(user_id, amount, reason=""):
    with get_db() as (conn, cur):
        if amount > 0:
            cur.execute("UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE user_id=?",
                        (amount, amount, user_id))
        else:
            cur.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
        if reason:
            cur.execute("INSERT INTO transactions(user_id,amount,reason) VALUES(?,?,?)",
                        (user_id, amount, reason))

def get_next_task(user_id):
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM tasks WHERE is_active=1 AND id NOT IN "
                    "(SELECT task_id FROM completed_tasks WHERE user_id=?) LIMIT 1", (user_id,))
        return dict_from_row(cur.fetchone())

def get_next_task_after(user_id, skip_id):
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM tasks WHERE is_active=1 AND id NOT IN "
                    "(SELECT task_id FROM completed_tasks WHERE user_id=?) AND id!=? LIMIT 1",
                    (user_id, skip_id))
        return dict_from_row(cur.fetchone())

def complete_task(user_id, task_id):
    with get_db() as (conn, cur):
        cur.execute("INSERT INTO completed_tasks(user_id,task_id,done_at) VALUES(?,?,?)",
                    (user_id, task_id, str(datetime.now())))

def claim_daily(user_id):
    user = get_user(user_id)
    today = str(date.today())
    yest = str(date.today() - timedelta(days=1))
    last = user.get("daily_claimed_at") or ""
    streak = user.get("daily_streak", 0)
    if last == today:
        return None, streak
    streak = (streak + 1) if last == yest else 1
    streak = min(streak, 7)
    reward = DAILY_REWARDS.get(streak, 0.10)
    with get_db() as (conn, cur):
        cur.execute("UPDATE users SET balance=balance+?, total_earned=total_earned+?, "
                    "daily_claimed_at=?, daily_streak=? WHERE user_id=?",
                    (reward, reward, today, streak, user_id))
        cur.execute("INSERT INTO transactions(user_id,amount,reason) VALUES(?,?,?)",
                    (user_id, reward, f"🎁 Ежедневка (серия {streak})"))
    return reward, streak

def do_tap(user_id):
    user = get_user(user_id)
    level = user.get("clicker_level", 1)
    earned = CLICKER_LEVELS[level]["per_tap"]
    with get_db() as (conn, cur):
        cur.execute("UPDATE users SET balance=balance+?, total_earned=total_earned+?, total_taps=total_taps+1 WHERE user_id=?",
                    (earned, earned, user_id))
    return earned, get_user(user_id)["balance"], level

def upgrade_clicker(user_id):
    user = get_user(user_id)
    level = user.get("clicker_level", 1)
    if level >= 7:
        return False, "🔱 Максимальный уровень!"
    cost = CLICKER_LEVELS[level]["upgrade"]
    if user["balance"] < cost:
        return False, f"❌ Нужно {cost} ⭐️, у тебя {user['balance']:.2f}"
    new_level = level + 1
    with get_db() as (conn, cur):
        cur.execute("UPDATE users SET clicker_level=?, balance=balance-? WHERE user_id=?",
                    (new_level, cost, user_id))
        cur.execute("INSERT INTO transactions(user_id,amount,reason) VALUES(?,?,?)",
                    (user_id, -cost, f"⬆️ Апгрейд кликера → ур.{new_level}"))
    return True, CLICKER_LEVELS[new_level]

def play_coinflip(user_id, bet, choice):
    result = random.choice(["heads", "tails"])
    win = (choice == result)
    if win:
        add_balance(user_id, bet, f"🪙 Монетка выиграл +{bet}")
        with get_db() as (conn, cur):
            cur.execute("UPDATE users SET pvp_wins=pvp_wins+1, pvp_total_bet=pvp_total_bet+? WHERE user_id=?", (bet, user_id))
    else:
        add_balance(user_id, -bet, f"🪙 Монетка проиграл -{bet}")
        with get_db() as (conn, cur):
            cur.execute("UPDATE users SET pvp_losses=pvp_losses+1, pvp_total_bet=pvp_total_bet+? WHERE user_id=?", (bet, user_id))
    return win, result

def play_slots(user_id, bet):
    symbols = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    mult = SLOT_PAYOUTS.get(tuple(symbols), 0)
    if mult > 0:
        winnings = round(bet * mult, 2)
        add_balance(user_id, winnings - bet, f"🎰 Слоты x{mult} +{winnings-bet:.2f}")
        with get_db() as (conn, cur):
            cur.execute("UPDATE users SET pvp_wins=pvp_wins+1, pvp_total_bet=pvp_total_bet+? WHERE user_id=?", (bet, user_id))
    else:
        add_balance(user_id, -bet, f"🎰 Слоты проиграл -{bet}")
        winnings = 0
        with get_db() as (conn, cur):
            cur.execute("UPDATE users SET pvp_losses=pvp_losses+1, pvp_total_bet=pvp_total_bet+? WHERE user_id=?", (bet, user_id))
    return symbols, mult, winnings

def create_duel(creator_id, bet):
    with get_db() as (conn, cur):
        cur.execute("INSERT INTO pvp_duels(creator_id,bet) VALUES(?,?)", (creator_id, bet))
        return cur.lastrowid

def get_open_duels():
    with get_db() as (conn, cur):
        cur.execute("SELECT d.*, u.first_name, u.username FROM pvp_duels d "
                    "JOIN users u ON d.creator_id=u.user_id WHERE d.status='open' "
                    "ORDER BY d.created_at DESC LIMIT 10")
        return [dict(r) for r in cur.fetchall()]

def accept_duel(duel_id, opponent_id):
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM pvp_duels WHERE id=? AND status='open'", (duel_id,))
        duel = cur.fetchone()
        if not duel:
            return None
        duel = dict(duel)
        if duel["creator_id"] == opponent_id:
            return None
        winner_id = random.choice([duel["creator_id"], opponent_id])
        loser_id = opponent_id if winner_id == duel["creator_id"] else duel["creator_id"]
        bet = duel["bet"]
        cur.execute("UPDATE pvp_duels SET status='done', opponent_id=?, winner_id=? WHERE id=?",
                    (opponent_id, winner_id, duel_id))
        cur.execute("UPDATE users SET balance=balance+?, total_earned=total_earned+?, pvp_wins=pvp_wins+1 WHERE user_id=?",
                    (bet, bet, winner_id))
        cur.execute("UPDATE users SET balance=balance-?, pvp_losses=pvp_losses+1 WHERE user_id=?",
                    (bet, loser_id))
        cur.execute("INSERT INTO transactions(user_id,amount,reason) VALUES(?,?,?)",
                    (winner_id, bet, f"⚔️ Дуэль #{duel_id} победа"))
        cur.execute("INSERT INTO transactions(user_id,amount,reason) VALUES(?,?,?)",
                    (loser_id, -bet, f"⚔️ Дуэль #{duel_id} поражение"))
        cur.execute("UPDATE users SET pvp_total_bet=pvp_total_bet+? WHERE user_id=?",
                    (bet, duel["creator_id"]))
        cur.execute("UPDATE users SET pvp_total_bet=pvp_total_bet+? WHERE user_id=?",
                    (bet, opponent_id))
        return winner_id, loser_id, bet

def cancel_duel(duel_id, user_id):
    with get_db() as (conn, cur):
        cur.execute("UPDATE pvp_duels SET status='cancelled' WHERE id=? AND creator_id=? AND status='open'",
                    (duel_id, user_id))

def get_top(field="balance", limit=10):
    with get_db() as (conn, cur):
        cur.execute(f"SELECT * FROM users WHERE is_banned=0 ORDER BY {field} DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

def get_all_users_ids():
    with get_db() as (conn, cur):
        cur.execute("SELECT user_id FROM users WHERE is_banned=0")
        return [r["user_id"] for r in cur.fetchall()]

def get_stats():
    with get_db() as (conn, cur):
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE is_banned=0")
        active = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE joined_at=?", (str(date.today()),))
        today = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(balance),0) FROM users")
        bal = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM completed_tasks")
        tasks = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM pvp_duels WHERE status='done'")
        duels = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(pvp_total_bet),0) FROM users")
        pvp_vol = cur.fetchone()[0]
        return total, active, today, bal, tasks, duels, pvp_vol

def use_promo(user_id, code):
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM promo_codes WHERE code=?", (code,))
        p = cur.fetchone()
        if not p:
            return False, 0, "❌ Промокод не найден!"
        p = dict(p)
        if p["used_count"] >= p["max_uses"]:
            return False, 0, "❌ Промокод исчерпан!"
        cur.execute("SELECT 1 FROM used_promos WHERE user_id=? AND code=?", (user_id, code))
        if cur.fetchone():
            return False, 0, "❌ Ты уже использовал этот промокод!"
        cur.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE code=?", (code,))
        cur.execute("INSERT INTO used_promos(user_id,code) VALUES(?,?)", (user_id, code))
        add_balance(user_id, p["reward"], f"🎫 Промокод {code}")
        return True, p["reward"], ""

def get_transactions(user_id, limit=10):
    with get_db() as (conn, cur):
        cur.execute("SELECT amount,reason,ts FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit))
        return [dict(r) for r in cur.fetchall()]

def find_user(query):
    with get_db() as (conn, cur):
        try:
            uid = int(query)
            cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        except ValueError:
            uname = query.lstrip("@")
            cur.execute("SELECT * FROM users WHERE username=?", (uname,))
        return dict_from_row(cur.fetchone())

# ══════════════════════════════════════════════════════════════
# 🧠 FSM (состояния в памяти)
# ══════════════════════════════════════════════════════════════

_states = {}

def set_state(uid, state, data=None):
    _states[uid] = {"state": state, "data": data or {}}

def get_state(uid):
    return _states.get(uid, {})

def clear_state(uid):
    _states.pop(uid, None)

# ══════════════════════════════════════════════════════════════
# ⌨️ КЛАВИАТУРЫ
# ══════════════════════════════════════════════════════════════

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚔️ PvP Арена"), KeyboardButton(text="✨ Кликер")],
        [KeyboardButton(text="⭐️ Заработать")],
        [KeyboardButton(text="🦁 Профиль"), KeyboardButton(text="💰 Вывод")],
        [KeyboardButton(text="📝 Задания"), KeyboardButton(text="📚 Инструкция")],
        [KeyboardButton(text="👑 Топ"), KeyboardButton(text="🏅 Достижения")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="💬 Отзывы")],
        [KeyboardButton(text="📊 История"), KeyboardButton(text="ℹ️ О боте")],
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Задания")],
        [KeyboardButton(text="➕ Добавить задание"), KeyboardButton(text="🎫 Создать промо")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="💰 Начислить")],
        [KeyboardButton(text="💸 Списать"), KeyboardButton(text="🔍 Найти юзера")],
        [KeyboardButton(text="🚫 Бан"), KeyboardButton(text="✅ Разбан")],
        [KeyboardButton(text="🏆 Топ баланс"), KeyboardButton(text="👥 Топ рефералы")],
        [KeyboardButton(text="📋 Список промо"), KeyboardButton(text="⚔️ Топ PvP")],
        [KeyboardButton(text="❌ Выйти из админки")],
    ], resize_keyboard=True)

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Промокод", callback_data="promo"),
         InlineKeyboardButton(text="🎁 Ежедневка", callback_data="daily")],
        [InlineKeyboardButton(text="💫 Перевести ⭐️ другу", callback_data="transfer")],
        [InlineKeyboardButton(text="📊 История транзакций", callback_data="history")],
        [InlineKeyboardButton(text="🔄 Обновить профиль", callback_data="refresh_profile")],
    ])

def clicker_kb(uid):
    user = get_user(uid)
    level = user.get("clicker_level", 1) if user else 1
    info = CLICKER_LEVELS[level]
    b = InlineKeyboardBuilder()
    b.button(text=f"👆 ТАП (+{info['per_tap']} ⭐️)", callback_data="tap")
    if level < 7:
        b.button(text=f"⬆️ Улучшить (−{info['upgrade']} ⭐️)", callback_data="upgrade_clicker")
    b.button(text="📊 Статистика кликера", callback_data="clicker_stats")
    b.adjust(1)
    return b.as_markup()

def pvp_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Дуэль (ставка vs игрок)", callback_data="pvp_duel_menu")],
        [InlineKeyboardButton(text="🪙 Орёл/Решка", callback_data="pvp_coin_menu")],
        [InlineKeyboardButton(text="🎰 Слоты", callback_data="pvp_slots_menu")],
        [InlineKeyboardButton(text="📋 Открытые дуэли", callback_data="pvp_open_duels")],
    ])

def coin_bet_kb():
    b = InlineKeyboardBuilder()
    for val in [0.5, 1, 2, 5, 10, 25, 50]:
        b.button(text=f"{val} ⭐️", callback_data=f"coin_bet_{val}")
    b.adjust(3)
    return b.as_markup()

def coin_side_kb(bet):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🦁 Лев (орёл)", callback_data=f"coin_heads_{bet}"),
         InlineKeyboardButton(text="👑 Корона (решка)", callback_data=f"coin_tails_{bet}")],
    ])

def slots_bet_kb():
    b = InlineKeyboardBuilder()
    for val in [0.5, 1, 2, 5, 10, 25, 50]:
        b.button(text=f"{val} ⭐️", callback_data=f"slots_bet_{val}")
    b.adjust(3)
    return b.as_markup()

def duel_bet_kb():
    b = InlineKeyboardBuilder()
    for val in [1, 2, 5, 10, 25, 50, 100]:
        b.button(text=f"{val} ⭐️", callback_data=f"duel_create_{val}")
    b.adjust(3)
    return b.as_markup()

def open_duels_kb(duels):
    b = InlineKeyboardBuilder()
    for d in duels:
        name = f"@{d['username']}" if d.get("username") else d.get("first_name", "?")
        b.button(text=f"⚔️ {name} — {d['bet']} ⭐️", callback_data=f"duel_accept_{d['id']}")
    b.button(text="🔄 Обновить", callback_data="pvp_open_duels")
    b.adjust(1)
    return b.as_markup()

def withdrawal_kb():
    b = InlineKeyboardBuilder()
    items = [
        ("15 ⭐️ (🧝)", 15), ("15 ⭐️ (💝)", 15),
        ("25 ⭐️ (🌹)", 25), ("25 ⭐️ (🎁)", 25),
        ("50 ⭐️ (🎷)", 50), ("50 ⭐️ (🎪)", 50),
        ("100 ⭐️ (🦁)", 100), ("100 ⭐️ (👑)", 100),
    ]
    for label, cost in items:
        b.button(text=label, callback_data=f"wd_{cost}")
    b.adjust(2)
    b.button(text="Telegram Premium — 3 мес. (900 ⭐️)", callback_data="wd_900")
    b.button(text="Telegram Premium — 6 мес. (1200 ⭐️)", callback_data="wd_1200")
    b.button(text="⬅️ Назад", callback_data="back_main")
    return b.as_markup()

def task_kb(task):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Подписаться", url=task["link"])],
        [InlineKeyboardButton(text="✅ Подтвердить подписку", callback_data=f"check_{task['id']}")],
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data=f"skip_{task['id']}")],
    ])

def top_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="👥 По рефералам", callback_data="top_refs")],
        [InlineKeyboardButton(text="⚔️ По PvP побед", callback_data="top_pvp"),
         InlineKeyboardButton(text="👆 По тапам", callback_data="top_taps")],
    ])

# ══════════════════════════════════════════════════════════════
# 🛡 АНТИБАН
# ══════════════════════════════════════════════════════════════

async def banned(msg: Message) -> bool:
    u = get_user(msg.from_user.id)
    if u and u.get("is_banned"):
        await msg.answer("🚫 Вы заблокированы в Lion Stars.")
        return True
    return False

# ══════════════════════════════════════════════════════════════
# 🚀 /start
# ══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    ref = None
    if len(args) > 1:
        try:
            ref = int(args[1])
        except ValueError:
            pass
    uid = message.from_user.id
    uname = message.from_user.username or ""
    fname = message.from_user.first_name or "Путник"
    user, is_new = get_or_create_user(uid, uname, fname, ref)
    if is_new and ref and ref != uid:
        try:
            await bot.send_message(ref, f"👑 <b>Lion Stars</b>\n\n🦁 По твоей ссылке пришёл <b>{fname}</b>!\n💰 +3.0 ⭐️ зачислено!", parse_mode="HTML")
        except Exception:
            pass
    await message.answer(
        f"👑 <b>Lion Stars</b> — Царство звёзд!\n\nПривет, <b>{fname}</b>! 🦁\n\n"
        "🔮 Приглашай друзей — <b>3 ⭐️ за каждого</b>\n"
        "✨ Тапай в кликере и качай уровень\n"
        "⚔️ Побеждай в PvP дуэлях и слотах\n"
        "🎁 Забирай ежедневный бонус (до 1 ⭐️ за серию)\n"
        "📝 Выполняй задания\n🏆 Борись за место в топе\n\n👇 Выбери раздел:",
        reply_markup=main_kb(), parse_mode="HTML")

# ══════════════════════════════════════════════════════════════
# 📋 ГЛАВНОЕ МЕНЮ — REPLY КНОПКИ
# ══════════════════════════════════════════════════════════════

@router.message(F.text == "🦁 Профиль")
async def btn_profile(message: Message):
    if await banned(message): return
    await send_profile(message, message.from_user.id)

async def send_profile(message, uid):
    user = get_user(uid)
    if not user:
        await message.answer("Напиши /start!")
        return
    uname = f"@{user['username']}" if user.get("username") else "не указан"
    level = user.get("clicker_level", 1)
    streak = user.get("daily_streak", 0)
    wins = user.get("pvp_wins", 0)
    losses = user.get("pvp_losses", 0)
    ratio = f"{wins}/{wins+losses}" if wins+losses else "0/0"
    text = (
        f"🦁 <b>Профиль Lion Stars</b>\n{'─'*28}\n"
        f"💬 Имя: {user['first_name']}\n🆔 ID: <code>{user['user_id']}</code>\n"
        f"👤 Username: {uname}\n📅 В боте с: {user.get('joined_at','—')}\n{'─'*28}\n"
        f"💰 Баланс: <b>{user['balance']:.2f} ⭐️</b>\n"
        f"📈 Всего заработано: {user.get('total_earned',0):.2f} ⭐️\n{'─'*28}\n"
        f"👥 Приглашено: {user['invited_count']} | Активных: {user['activated_count']}\n"
        f"✨ Кликер: <b>{CLICKER_LEVELS[level]['name']}</b> (ур.{level})\n"
        f"👆 Тапов: {user.get('total_taps',0)}\n⚔️ PvP: {ratio} (W/L)\n"
        f"🔥 Серия ежедневок: {streak} дн."
    )
    await message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")

@router.message(F.text == "⭐️ Заработать")
async def btn_earn(message: Message):
    if await banned(message): return
    uid = message.from_user.id
    await message.answer(
        f"👑 <b>Реферальная программа Lion Stars</b>\n\n"
        f"🔗 Твоя ссылка:\n<code>https://t.me/{BOT_USERNAME}?start={uid}</code>\n\n"
        f"За каждого нового друга — <b>3 ⭐️</b>!\n\n"
        "💡 <b>Как заработать больше:</b>\n"
        "• Поставь ссылку в bio Telegram (+1 ⭐️/день)\n"
        "• Выложи видео в TikTok/Reels/Shorts\n"
        "• Поделись в чатах и группах\n• Выполняй задания",
        parse_mode="HTML")

@router.message(F.text == "✨ Кликер")
async def btn_clicker(message: Message):
    if await banned(message): return
    await send_clicker(message, message.from_user.id)

async def send_clicker(message, uid):
    user = get_user(uid)
    level = user.get("clicker_level", 1)
    info = CLICKER_LEVELS[level]
    next_info = CLICKER_LEVELS.get(level+1)
    upgrade_line = ""
    if next_info:
        upgrade_line = f"\n⬆️ Следующий: <b>{next_info['name']}</b> (+{next_info['per_tap']} ⭐️/тап) за {info['upgrade']} ⭐️"
    await message.answer(
        f"✨ <b>Кликер Lion Stars</b>\n{'─'*28}\n"
        f"🏅 Уровень: <b>{info['name']}</b> ({level}/7)\n"
        f"👆 За тап: <b>{info['per_tap']} ⭐️</b>\n"
        f"💰 Баланс: <b>{user['balance']:.2f} ⭐️</b>\n"
        f"🖱 Тапов всего: {user.get('total_taps',0)}{upgrade_line}\n\n"
        "👇 Жми ТАП и зарабатывай!",
        reply_markup=clicker_kb(uid), parse_mode="HTML")

@router.message(F.text == "⚔️ PvP Арена")
async def btn_pvp(message: Message):
    if await banned(message): return
    user = get_user(message.from_user.id)
    wins = user.get("pvp_wins",0) if user else 0
    losses = user.get("pvp_losses",0) if user else 0
    await message.answer(
        f"⚔️ <b>PvP Арена Lion Stars</b>\n{'─'*28}\n"
        f"🏆 Твой счёт: {wins}W / {losses}L\n💰 Баланс: {user['balance']:.2f} ⭐️\n{'─'*28}\n\n"
        "⚔️ <b>Дуэль</b> — брось вызов игроку, победитель забирает ставку\n"
        "🪙 <b>Монетка</b> — Лев или Корона? x2 при победе!\n"
        "🎰 <b>Слоты</b> — три символа, до x10!\n\n👇 Выбери режим:",
        reply_markup=pvp_menu_kb(), parse_mode="HTML")

@router.message(F.text == "📝 Задания")
async def btn_tasks(message: Message):
    if await banned(message): return
    task = get_next_task(message.from_user.id)
    if not task:
        await message.answer("✨ Все задания выполнены!\nНовые появятся скоро. 🦁")
        return
    await send_task_msg(message, task)

async def send_task_msg(message, task):
    await message.answer(
        f"📝 <b>Новое задание!</b>\n{'─'*28}\n🎯 {task['text']}\n💰 Награда: <b>{task['reward']} ⭐️</b>\n\n"
        "⚠️ Подпишись и не отписывайся 7 дней!",
        reply_markup=task_kb(task), parse_mode="HTML")

@router.message(F.text == "💰 Вывод")
async def btn_withdrawal(message: Message):
    if await banned(message): return
    user = get_user(message.from_user.id)
    await message.answer(f"💰 <b>Вывод звёзд</b>\n\nБаланс: <b>{user['balance']:.2f} ⭐️</b>\n\nВыбери подарок:",
                         reply_markup=withdrawal_kb(), parse_mode="HTML")

@router.message(F.text == "👑 Топ")
async def btn_top(message: Message):
    if await banned(message): return
    await send_top(message, "balance")

async def send_top(message, field):
    top = get_top(field, 10)
    titles = {"balance":"💰 Топ 10 по балансу","activated_count":"👥 Топ 10 по рефералам",
              "pvp_wins":"⚔️ Топ 10 по PvP победам","total_taps":"👆 Топ 10 по тапам"}
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines = [f"<b>{titles.get(field,'🏆 Топ 10')}:</b>\n"]
    for i, u in enumerate(top):
        name = f"@{u['username']}" if u.get("username") else u.get("first_name","—")
        val = {"balance":f"{u['balance']:.1f} ⭐️","activated_count":f"{u['activated_count']} реф.",
               "pvp_wins":f"{u['pvp_wins']} побед","total_taps":f"{u['total_taps']} тапов"}.get(field,"—")
        lines.append(f"{medals[i]} {name} — {val}")
    lines.append("\n🦁 Борись за корону!")
    await message.answer("\n".join(lines), reply_markup=top_kb(), parse_mode="HTML")

@router.message(F.text == "🏅 Достижения")
async def btn_achievements(message: Message):
    if await banned(message): return
    user = get_user(message.from_user.id)
    if not user: return
    def b(cond): return "✅" if cond else "⬜"
    taps, refs, earned = user.get("total_taps",0), user.get("activated_count",0), user.get("total_earned",0)
    level, streak, wins = user.get("clicker_level",1), user.get("daily_streak",0), user.get("pvp_wins",0)
    await message.answer(
        f"🏅 <b>Достижения Lion Stars</b>\n{'─'*28}\n\n"
        f"<b>👆 Кликер:</b>\n{b(taps>=1)} Первый тап\n{b(taps>=100)} 100 тапов\n{b(taps>=1000)} 1 000 тапов\n{b(taps>=10000)} 10 000 тапов — Пощёчина льва\n\n"
        f"<b>👥 Рефералы:</b>\n{b(refs>=1)} Первый реферал\n{b(refs>=5)} 5 рефералов\n{b(refs>=25)} 25 рефералов — Вождь\n{b(refs>=100)} 100 рефералов — Король племени\n\n"
        f"<b>💰 Заработок:</b>\n{b(earned>=10)} 10 ⭐️ заработано\n{b(earned>=100)} 100 ⭐️ заработано\n{b(earned>=500)} 500 ⭐️ — Богатый лев\n{b(earned>=1000)} 1 000 ⭐️ — Царь зверей\n\n"
        f"<b>🔥 Серия:</b>\n{b(streak>=3)} Серия 3 дня\n{b(streak>=7)} Серия 7 дней — Верный\n\n"
        f"<b>⚔️ PvP:</b>\n{b(wins>=1)} Первая победа\n{b(wins>=10)} 10 побед\n{b(wins>=50)} 50 побед — Гладиатор\n\n"
        f"<b>✨ Кликер уровни:</b>\n{b(level>=3)} Уровень 3 — Принц\n{b(level>=5)} Уровень 5 — Вождь\n{b(level>=7)} Уровень 7 — Император 🔱",
        parse_mode="HTML")

@router.message(F.text == "📊 История")
async def btn_history(message: Message):
    if await banned(message): return
    txs = get_transactions(message.from_user.id, 15)
    if not txs:
        await message.answer("📊 История транзакций пуста.")
        return
    lines = ["📊 <b>Последние 15 транзакций:</b>\n"]
    for t in txs:
        sign = "+" if t["amount"]>=0 else ""
        lines.append(f"{sign}{t['amount']:.2f} ⭐️  {t['reason']}  <i>({t['ts'][:10]})</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(F.text == "📚 Инструкция")
async def btn_inst(message: Message):
    await message.answer(
        "📌 <b>Как заработать в Lion Stars?</b>\n\n"
        "1️⃣ Скопируй реферальную ссылку в «Заработать»\n"
        "2️⃣ Вставь в bio Telegram (+1 ⭐️/день)\n"
        "3️⃣ Сними видео в TikTok/Reels — вставь ссылку\n"
        "4️⃣ Тапай в кликере до Императора (1 ⭐️/тап)\n"
        "5️⃣ Играй в PvP — удваивай звёзды\n"
        "6️⃣ Выполняй задания каждый день\n"
        "7️⃣ Не пропускай ежедневку (серия до 1 ⭐️!)\n\n🏆 Попади в топ — получи приз!",
        parse_mode="HTML")

@router.message(F.text.in_({"ℹ️ О боте","🛒 Магазин","💬 Отзывы"}))
async def btn_info(message: Message):
    await message.answer("👑 Lion Stars\nОфициальный канал и магазин: @patrickstarsfarm\nОтзывы: @patrickstars_reviews")

# ══════════════════════════════════════════════════════════════
# INLINE CALLBACKS (полные, как раньше)
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "tap")
async def cb_tap(cb: CallbackQuery):
    earned, bal, _ = do_tap(cb.from_user.id)
    await cb.answer(f"👆 +{earned} ⭐️ | 💰 {bal:.2f} ⭐️")

@router.callback_query(F.data == "upgrade_clicker")
async def cb_upgrade(cb: CallbackQuery):
    ok, result = upgrade_clicker(cb.from_user.id)
    if ok:
        info = result
        await cb.answer(f"✅ Апгрейд до {info['name']}!\n+{info['per_tap']} ⭐️ за тап", show_alert=True)
        await send_clicker(cb.message, cb.from_user.id)
    else:
        await cb.answer(result, show_alert=True)

@router.callback_query(F.data == "clicker_stats")
async def cb_clicker_stats(cb: CallbackQuery):
    user = get_user(cb.from_user.id)
    level = user.get("clicker_level",1)
    info = CLICKER_LEVELS[level]
    await cb.answer(f"🏅 {info['name']} (ур.{level}/7)\n👆 За тап: {info['per_tap']} ⭐️\n🖱 Тапов: {user.get('total_taps',0)}\n💰 Баланс: {user['balance']:.2f} ⭐️", show_alert=True)

# PvP
@router.callback_query(F.data == "pvp_coin_menu")
async def cb_coin_menu(cb: CallbackQuery):
    await cb.message.answer("🪙 <b>Орёл/Решка</b>\n\nВыбери ставку:", reply_markup=coin_bet_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("coin_bet_"))
async def cb_coin_bet(cb: CallbackQuery):
    bet = float(cb.data.split("_")[-1])
    user = get_user(cb.from_user.id)
    if not user or user["balance"] < bet:
        await cb.answer(f"❌ Недостаточно звёзд! Нужно {bet} ⭐️", show_alert=True)
        return
    await cb.message.answer(f"🪙 Ставка: <b>{bet} ⭐️</b>\n\nВыбери сторону:", reply_markup=coin_side_kb(bet), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("coin_heads_") | F.data.startswith("coin_tails_"))
async def cb_coin_play(cb: CallbackQuery):
    parts = cb.data.split("_")
    choice = parts[1]
    bet = float(parts[2])
    user = get_user(cb.from_user.id)
    if not user or user["balance"] < bet:
        await cb.answer("❌ Недостаточно звёзд!", show_alert=True)
        return
    add_balance(cb.from_user.id, -bet)
    win, result = play_coinflip(cb.from_user.id, bet, choice)
    side_names = {"heads":"🦁 Лев","tails":"👑 Корона"}
    if win:
        text = f"🪙 <b>Орёл/Решка</b>\n\nВыпало: {side_names[result]}\nТвой выбор: {side_names[choice]}\n\n🎉 <b>ПОБЕДА!</b> +{bet} ⭐️\n💰 Баланс: {get_user(cb.from_user.id)['balance']:.2f} ⭐️"
    else:
        text = f"🪙 <b>Орёл/Решка</b>\n\nВыпало: {side_names[result]}\nТвой выбор: {side_names[choice]}\n\n😔 <b>ПОРАЖЕНИЕ!</b> -{bet} ⭐️\n💰 Баланс: {get_user(cb.from_user.id)['balance']:.2f} ⭐️"
    await cb.message.answer(text, reply_markup=coin_bet_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "pvp_slots_menu")
async def cb_slots_menu(cb: CallbackQuery):
    await cb.message.answer("🎰 <b>Слоты Lion Stars</b>\n\n<b>Таблица выплат:</b>\n🔱🔱🔱 — x10\n💎💎💎 — x7\n👑👑👑 — x5\n🦁🦁🦁 — x4\n🌟🌟🌟 — x3\n⭐️⭐️⭐️ — x2\n\nВыбери ставку:", reply_markup=slots_bet_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("slots_bet_"))
async def cb_slots_play(cb: CallbackQuery):
    bet = float(cb.data.split("_")[-1])
    user = get_user(cb.from_user.id)
    if not user or user["balance"] < bet:
        await cb.answer(f"❌ Недостаточно звёзд! Нужно {bet} ⭐️", show_alert=True)
        return
    add_balance(cb.from_user.id, -bet)
    symbols, mult, winnings = play_slots(cb.from_user.id, bet)
    sym_str = " | ".join(symbols)
    bal = get_user(cb.from_user.id)["balance"]
    if mult > 0:
        text = f"🎰 <b>Слоты</b>\n\n[ {sym_str} ]\n\n🎉 <b>ВЫИГРЫШ x{mult}!</b>\n+{winnings:.2f} ⭐️\n💰 Баланс: {bal:.2f} ⭐️"
    else:
        text = f"🎰 <b>Слоты</b>\n\n[ {sym_str} ]\n\n😔 Не повезло...\n-{bet} ⭐️\n💰 Баланс: {bal:.2f} ⭐️"
    await cb.message.answer(text, reply_markup=slots_bet_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "pvp_duel_menu")
async def cb_duel_menu(cb: CallbackQuery):
    await cb.message.answer("⚔️ <b>Дуэль</b>\n\nСоздай дуэль — другой игрок примет её.\nПобедитель определяется случайно!\n\nВыбери ставку:", reply_markup=duel_bet_kb(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("duel_create_"))
async def cb_duel_create(cb: CallbackQuery):
    bet = float(cb.data.split("_")[-1])
    user = get_user(cb.from_user.id)
    if not user or user["balance"] < bet:
        await cb.answer(f"❌ Нужно {bet} ⭐️", show_alert=True)
        return
    add_balance(cb.from_user.id, -bet, f"⚔️ Создание дуэли ({bet} ⭐️)")
    duel_id = create_duel(cb.from_user.id, bet)
    fname = cb.from_user.first_name or "Игрок"
    uname = f"@{cb.from_user.username}" if cb.from_user.username else fname
    await cb.message.answer(f"⚔️ <b>Дуэль создана!</b>\n\n🦁 Создатель: {uname}\n💰 Ставка: {bet} ⭐️\n🆔 ID дуэли: #{duel_id}\n\nОжидаю соперника...\n\nПоделись ссылкой:\n<code>https://t.me/{BOT_USERNAME}?start=duel_{duel_id}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить дуэль", callback_data=f"duel_cancel_{duel_id}")]]), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "pvp_open_duels")
async def cb_open_duels(cb: CallbackQuery):
    duels = get_open_duels()
    if not duels:
        await cb.message.answer("⚔️ Открытых дуэлей нет.\nСоздай первую!", reply_markup=duel_bet_kb())
        await cb.answer()
        return
    await cb.message.answer(f"⚔️ <b>Открытые дуэли ({len(duels)}):</b>\n\nВыбери и прими:", reply_markup=open_duels_kb(duels), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("duel_accept_"))
async def cb_duel_accept(cb: CallbackQuery):
    duel_id = int(cb.data.split("_")[-1])
    result = accept_duel(duel_id, cb.from_user.id)
    if result is None:
        await cb.answer("❌ Дуэль недоступна", show_alert=True)
        return
    winner_id, loser_id, bet = result
    winner = get_user(winner_id)
    loser = get_user(loser_id)
    text = f"⚔️ <b>Дуэль #{duel_id} завершена!</b>\n\n🏆 Победитель: <b>{winner.get('first_name','Игрок')}</b> +{bet} ⭐️\n💔 Проиграл: {loser.get('first_name','Игрок')} -{bet} ⭐️"
    await cb.message.answer(text, parse_mode="HTML")
    try:
        await bot.send_message(winner_id if winner_id!=cb.from_user.id else loser_id, text, parse_mode="HTML")
    except: pass
    await cb.answer()

@router.callback_query(F.data.startswith("duel_cancel_"))
async def cb_duel_cancel(cb: CallbackQuery):
    duel_id = int(cb.data.split("_")[-1])
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM pvp_duels WHERE id=? AND creator_id=? AND status='open'", (duel_id, cb.from_user.id))
        duel = cur.fetchone()
    if not duel:
        await cb.answer("❌ Дуэль не найдена", show_alert=True)
        return
    cancel_duel(duel_id, cb.from_user.id)
    add_balance(cb.from_user.id, duel["bet"], "⚔️ Возврат ставки (отмена дуэли)")
    await cb.answer("✅ Дуэль отменена, ставка возвращена", show_alert=True)
    await cb.message.delete()

# Профиль
@router.callback_query(F.data == "daily")
async def cb_daily(cb: CallbackQuery):
    reward, streak = claim_daily(cb.from_user.id)
    if reward is None:
        await cb.answer("⏳ Ты уже забирал бонус сегодня!\nПриходи завтра 🦁", show_alert=True)
        return
    next_r = DAILY_REWARDS.get(min(streak+1,7),1.0)
    await cb.answer(f"👑 Lion Stars\n\n✅ +{reward} ⭐️\n🔥 Серия: {streak} дн.\nЗавтра: +{next_r} ⭐️ (не пропусти!)", show_alert=True)

@router.callback_query(F.data == "promo")
async def cb_promo(cb: CallbackQuery):
    set_state(cb.from_user.id, "wait_promo")
    await cb.message.answer("🎫 Введи промокод:")
    await cb.answer()

@router.callback_query(F.data == "transfer")
async def cb_transfer(cb: CallbackQuery):
    set_state(cb.from_user.id, "wait_transfer_id")
    await cb.message.answer("💫 Введи Telegram ID пользователя для перевода:")
    await cb.answer()

@router.callback_query(F.data == "history")
async def cb_history(cb: CallbackQuery):
    txs = get_transactions(cb.from_user.id, 10)
    if not txs:
        await cb.answer("История пуста", show_alert=True)
        return
    lines = ["📊 <b>Последние транзакции:</b>\n"]
    for t in txs:
        sign = "+" if t["amount"]>=0 else ""
        lines.append(f"{sign}{t['amount']:.2f} ⭐️  {t['reason']}")
    await cb.message.answer("\n".join(lines), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "refresh_profile")
async def cb_refresh_profile(cb: CallbackQuery):
    await send_profile(cb.message, cb.from_user.id)
    await cb.answer("🔄 Обновлено!")

# Топ
@router.callback_query(F.data.in_({"top_balance","top_refs","top_pvp","top_taps"}))
async def cb_top(cb: CallbackQuery):
    mapping = {"top_balance":"balance","top_refs":"activated_count","top_pvp":"pvp_wins","top_taps":"total_taps"}
    await send_top(cb.message, mapping[cb.data])
    await cb.answer()

# Задания
@router.callback_query(F.data.startswith("check_"))
async def cb_check(cb: CallbackQuery):
    task_id = int(cb.data.split("_")[1])
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        task = cur.fetchone()
    if not task:
        await cb.answer("Задание не найдено!", show_alert=True)
        return
    task = dict(task)
    try:
        member = await bot.get_chat_member(chat_id=task["channel_id"], user_id=cb.from_user.id)
        is_member = member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.BANNED)
    except Exception as e:
        logger.warning(f"get_chat_member error: {e}")
        await cb.answer("❌ Не удалось проверить подписку", show_alert=True)
        return
    if is_member:
        complete_task(cb.from_user.id, task_id)
        add_balance(cb.from_user.id, task["reward"], f"📝 Задание: {task['text'][:30]}")
        await cb.answer(f"✅ +{task['reward']} ⭐️ Задание выполнено!", show_alert=True)
        nxt = get_next_task(cb.from_user.id)
        if nxt:
            await send_task_msg(cb.message, nxt)
        else:
            await cb.message.answer("🎉 Все задания выполнены! Загляни позже 🦁")
    else:
        await cb.answer("❌ Ты не подписался на канал!", show_alert=True)

@router.callback_query(F.data.startswith("skip_"))
async def cb_skip(cb: CallbackQuery):
    skip_id = int(cb.data.split("_")[1])
    task = get_next_task_after(cb.from_user.id, skip_id)
    if task:
        await send_task_msg(cb.message, task)
    else:
        await cb.message.answer("✨ Больше нет доступных заданий.")
    await cb.answer()

# Вывод
@router.callback_query(F.data.startswith("wd_"))
async def cb_wd(cb: CallbackQuery):
    cost = int(cb.data.split("_")[1])
    user = get_user(cb.from_user.id)
    if not user or user["balance"] < cost:
        await cb.answer(f"❌ Недостаточно звёзд! Нужно {cost} ⭐️", show_alert=True)
        return
    await cb.answer(f"✅ Заявка на {cost} ⭐️ принята! Ожидай.", show_alert=True)
    await bot.send_message(ADMIN_ID, f"📤 <b>Заявка на вывод!</b>\n👤 @{cb.from_user.username or '—'} (<code>{cb.from_user.id}</code>)\n💰 {cost} ⭐️ | Баланс: {user['balance']:.2f} ⭐️", parse_mode="HTML")

# Админ удаление задания
@router.callback_query(F.data.startswith("adm_del_"))
async def cb_adm_del(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    task_id = int(cb.data.split("_")[-1])
    with get_db() as (conn, cur):
        cur.execute("UPDATE tasks SET is_active=0 WHERE id=?", (task_id,))
    await cb.answer(f"✅ Задание #{task_id} деактивировано!", show_alert=True)
    try: await cb.message.delete()
    except: pass

# ══════════════════════════════════════════════════════════════
# 👑 /admin
# ══════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Нет доступа.")
        return
    set_state(message.from_user.id, "in_admin")
    await message.answer("👑 <b>Панель администратора</b>", reply_markup=admin_kb(), parse_mode="HTML")

# ══════════════════════════════════════════════════════════════
# 📨 ОБРАБОТКА ВСЕХ СООБЩЕНИЙ (FSM + АДМИНКА)
# ══════════════════════════════════════════════════════════════

@router.message()
async def handle_all(message: Message):
    uid = message.from_user.id
    text = message.text or ""
    st = get_state(uid).get("state", "")
    data = get_state(uid).get("data", {})
    is_admin = uid == ADMIN_ID

    if text == "❌ Выйти из админки" and is_admin:
        clear_state(uid)
        await message.answer("👋 Вышел из админ-панели.", reply_markup=main_kb())
        return

    # Пользовательские состояния
    if st == "wait_promo":
        clear_state(uid)
        ok, reward, err = use_promo(uid, text.strip())
        await message.answer(f"🎉 Промокод активирован! +{reward} ⭐️" if ok else err)
        return
    if st == "wait_transfer_id":
        try:
            target_id = int(text.strip())
        except ValueError:
            await message.answer("❌ ID — только цифры.")
            return
        target = get_user(target_id)
        if not target:
            await message.answer("❌ Пользователь не найден.")
            clear_state(uid)
            return
        set_state(uid, "wait_transfer_amount", {"target_id": target_id, "target_name": target["first_name"]})
        await message.answer(f"💫 Перевод → <b>{target['first_name']}</b>\nВведи количество ⭐️:", parse_mode="HTML")
        return
    if st == "wait_transfer_amount":
        try:
            amount = float(text.strip().replace(",","."))
        except ValueError:
            await message.answer("❌ Введи число.")
            return
        user = get_user(uid)
        if not user or user["balance"] < amount:
            await message.answer("❌ Недостаточно звёзд!")
            clear_state(uid)
            return
        target_id = data["target_id"]
        add_balance(uid, -amount, f"💫 Перевод → {target_id}")
        add_balance(target_id, amount, f"💫 Перевод ← {uid}")
        clear_state(uid)
        await message.answer(f"✅ Переведено {amount} ⭐️ → {data['target_name']}!")
        try:
            await bot.send_message(target_id, f"💫 Тебе перевели <b>{amount} ⭐️</b> от @{message.from_user.username or uid}!", parse_mode="HTML")
        except: pass
        return

    # Админка
    if is_admin and st in ("in_admin","") or (st and st.startswith("adm_")):
        if text == "📊 Статистика":
            total, active, today, bal, tasks, duels, pvp_vol = get_stats()
            await message.answer(
                f"📊 <b>Статистика</b>\n{'─'*28}\n"
                f"👥 Всего: {total}\n✅ Активных: {active}\n🆕 Сегодня: {today}\n"
                f"💰 Суммарный баланс: {bal:.2f} ⭐️\n📝 Заданий выполнено: {tasks}\n"
                f"⚔️ PvP дуэлей: {duels}\n📈 Оборот PvP: {pvp_vol:.2f} ⭐️\n"
                f"💾 БД: SQLite в /data/lionstars.db",
                parse_mode="HTML")
            return

        if text == "👥 Задания":
            with get_db() as (conn, cur):
                cur.execute("SELECT * FROM tasks ORDER BY id")
                tasks_list = [dict(r) for r in cur.fetchall()]
            if not tasks_list:
                await message.answer("Заданий нет.")
                return
            lines = ["📝 <b>Все задания:</b>\n"]
            b = InlineKeyboardBuilder()
            for t in tasks_list:
                s = "✅" if t["is_active"] else "❌"
                lines.append(f"{s} #{t['id']} | {t['text']} | {t['reward']} ⭐️")
                if t["is_active"]:
                    b.button(text=f"🗑 #{t['id']} {t['text'][:20]}", callback_data=f"adm_del_{t['id']}")
            b.adjust(1)
            kb = b.as_markup() if any(t["is_active"] for t in tasks_list) else None
            await message.answer("\n".join(lines), reply_markup=kb, parse_mode="HTML")
            return

        if text == "➕ Добавить задание":
            set_state(uid, "adm_task_text")
            await message.answer("✏️ Введи название задания:")
            return
        if st == "adm_task_text":
            set_state(uid, "adm_task_reward", {"text": text})
            await message.answer("💰 Введи награду (например 0.5):")
            return
        if st == "adm_task_reward":
            try: reward = float(text.replace(",","."))
            except: await message.answer("❌ Введи число."); return
            d = data; d["reward"] = reward
            set_state(uid, "adm_task_link", d)
            await message.answer("🔗 Введи ссылку на канал:")
            return
        if st == "adm_task_link":
            d = data; d["link"] = text.strip()
            set_state(uid, "adm_task_cid", d)
            await message.answer("🆔 Введи ID канала (-100...):")
            return
        if st == "adm_task_cid":
            d = data
            with get_db() as (conn, cur):
                cur.execute("INSERT INTO tasks(text,reward,link,channel_id) VALUES(?,?,?,?)",
                            (d["text"], d["reward"], d["link"], text.strip()))
            set_state(uid, "in_admin")
            await message.answer("✅ Задание добавлено!")
            return

        if text == "🎫 Создать промо":
            set_state(uid, "adm_promo_code")
            await message.answer("🎫 Введи код:")
            return
        if st == "adm_promo_code":
            set_state(uid, "adm_promo_reward", {"code": text.strip()})
            await message.answer("💰 Введи награду:")
            return
        if st == "adm_promo_reward":
            try: reward = float(text.replace(",","."))
            except: await message.answer("❌ Введи число."); return
            d = data; d["reward"] = reward
            set_state(uid, "adm_promo_uses", d)
            await message.answer("🔢 Макс. использований:")
            return
        if st == "adm_promo_uses":
            try: uses = int(text.strip())
            except: await message.answer("❌ Целое число."); return
            d = data
            with get_db() as (conn, cur):
                cur.execute("INSERT INTO promo_codes(code,reward,max_uses,used_count) VALUES(?,?,?,0)",
                            (d["code"], d["reward"], uses))
            set_state(uid, "in_admin")
            await message.answer(f"✅ Промокод <code>{d['code']}</code> создан! ({d['reward']} ⭐️, {uses} исп.)", parse_mode="HTML")
            return

        if text == "📋 Список промо":
            with get_db() as (conn, cur):
                cur.execute("SELECT * FROM promo_codes ORDER BY code")
                promos = [dict(r) for r in cur.fetchall()]
            if not promos:
                await message.answer("Промокодов нет.")
                return
            lines = ["🎫 <b>Все промокоды:</b>\n"]
            for p in promos:
                lines.append(f"<code>{p['code']}</code> — {p['reward']} ⭐️ | {p['used_count']}/{p['max_uses']}")
            await message.answer("\n".join(lines), parse_mode="HTML")
            return

        if text == "📢 Рассылка":
            set_state(uid, "adm_broadcast")
            await message.answer("📢 Введи текст рассылки (HTML):")
            return
        if st == "adm_broadcast":
            all_ids = get_all_users_ids()
            set_state(uid, "in_admin")
            sent, fail = 0, 0
            for tid in all_ids:
                try:
                    await bot.send_message(tid, text, parse_mode="HTML")
                    sent += 1
                    await asyncio.sleep(0.04)
                except: fail += 1
            await message.answer(f"✅ Рассылка завершена: {sent} ✓ | {fail} ✗")
            return

        if text == "💰 Начислить":
            set_state(uid, "adm_give_id")
            await message.answer("🆔 ID пользователя:")
            return
        if st == "adm_give_id":
            try: target_id = int(text.strip())
            except: await message.answer("❌ Неверный ID."); return
            set_state(uid, "adm_give_amount", {"target_id": target_id})
            await message.answer("💰 Сумма для начисления:")
            return
        if st == "adm_give_amount":
            try: amount = float(text.replace(",","."))
            except: await message.answer("❌ Введи число."); return
            add_balance(data["target_id"], amount, "🎁 Начисление администратором")
            set_state(uid, "in_admin")
            await message.answer(f"✅ Начислено {amount} ⭐️ → {data['target_id']}!")
            try: await bot.send_message(data["target_id"], f"🎁 Администратор начислил тебе <b>{amount} ⭐️</b>!", parse_mode="HTML")
            except: pass
            return

        if text == "💸 Списать":
            set_state(uid, "adm_take_id")
            await message.answer("🆔 ID:")
            return
        if st == "adm_take_id":
            try: target_id = int(text.strip())
            except: await message.answer("❌ Неверный ID."); return
            set_state(uid, "adm_take_amount", {"target_id": target_id})
            await message.answer("💸 Сумма списания:")
            return
        if st == "adm_take_amount":
            try: amount = float(text.replace(",","."))
            except: await message.answer("❌ Введи число."); return
            add_balance(data["target_id"], -amount, "💸 Списание администратором")
            set_state(uid, "in_admin")
            await message.answer(f"✅ Списано {amount} ⭐️ у {data['target_id']}!")
            return

        if text == "🔍 Найти юзера":
            set_state(uid, "adm_find")
            await message.answer("🔍 Введи ID или @username:")
            return
        if st == "adm_find":
            u = find_user(text.strip())
            set_state(uid, "in_admin")
            if not u:
                await message.answer("❌ Пользователь не найден.")
                return
            await message.answer(
                f"🔍 <b>Пользователь</b>\n🆔 <code>{u['user_id']}</code>\n"
                f"👤 @{u.get('username','—')} | {u.get('first_name','—')}\n"
                f"💰 Баланс: {u['balance']:.2f} ⭐️\n📈 Заработано: {u.get('total_earned',0):.2f} ⭐️\n"
                f"👥 Рефералов: {u['activated_count']}\n⚔️ PvP: {u.get('pvp_wins',0)}W/{u.get('pvp_losses',0)}L\n"
                f"👆 Тапов: {u.get('total_taps',0)}\n✨ Кликер ур.{u.get('clicker_level',1)}\n"
                f"📅 В боте с: {u.get('joined_at','—')}\n🚫 Бан: {'Да' if u.get('is_banned') else 'Нет'}",
                parse_mode="HTML")
            return

        if text == "🚫 Бан":
            set_state(uid, "adm_ban")
            await message.answer("🚫 Введи ID для бана:")
            return
        if st == "adm_ban":
            try: target_id = int(text.strip())
            except: await message.answer("❌ Неверный ID."); set_state(uid, "in_admin"); return
            with get_db() as (conn, cur):
                cur.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (target_id,))
            set_state(uid, "in_admin")
            await message.answer(f"🚫 Пользователь {target_id} заблокирован.")
            return

        if text == "✅ Разбан":
            set_state(uid, "adm_unban")
            await message.answer("✅ Введи ID для разбана:")
            return
        if st == "adm_unban":
            try: target_id = int(text.strip())
            except: await message.answer("❌ Неверный ID."); set_state(uid, "in_admin"); return
            with get_db() as (conn, cur):
                cur.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (target_id,))
            set_state(uid, "in_admin")
            await message.answer(f"✅ Пользователь {target_id} разблокирован.")
            return

        if text in ("🏆 Топ баланс","👥 Топ рефералы","⚔️ Топ PvP"):
            field = {"🏆 Топ баланс":"balance","👥 Топ рефералы":"activated_count","⚔️ Топ PvP":"pvp_wins"}[text]
            top = get_top(field, 10)
            lines = [f"<b>{text}:</b>\n"]
            for i, u in enumerate(top,1):
                name = f"@{u['username']}" if u.get("username") else u.get("first_name","—")
                val = {"balance":f"{u['balance']:.2f} ⭐️","activated_count":f"{u['activated_count']} реф.","pvp_wins":f"{u['pvp_wins']}W/{u['pvp_losses']}L"}[field]
                lines.append(f"{i}. {name} — {val} | ID {u['user_id']}")
            await message.answer("\n".join(lines), parse_mode="HTML")
            return

# ══════════════════════════════════════════════════════════════
# 🚀 ЗАПУСК
# ══════════════════════════════════════════════════════════════

async def run_polling():
    init_db()
    logger.info("🚀 Polling mode...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def run_webhook():
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    init_db()
    logger.info(f"🚀 Webhook mode → {WEBHOOK_URL}")
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    app = web.Application()
    app.router.add_get("/", lambda _: web.Response(text="🦁 Lion Stars OK"))
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT).start()
    logger.info(f"🌐 Listening on {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    try: await asyncio.Event().wait()
    finally: await runner.cleanup(); await bot.delete_webhook()

if __name__ == "__main__":
    asyncio.run(run_webhook() if USE_WEBHOOK else run_polling())
