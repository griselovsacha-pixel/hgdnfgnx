import os
import sqlite3
import logging
import datetime
import time
import random
from typing import Optional, List, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# ==========================================
# ⚙️ НАСТРОЙКИ ПРОЕКТА LION STARS
# ==========================================
BOT_TOKEN = "8989832302:AAHWAAbab8xTqHZsqvwwH2MCoOQl1RsrCPE"
BOT_USERNAME = "ИМЯ_ТВОЕГО_БОТА"  # Укажи имя бота без @
DB_NAME = "lion_stars.db"
ADMIN_ID = 880628963            # Замени на свой Telegram ID

# Константы игрового баланса
REFERRAL_WELCOME_BONUS = 1.0     # Бонус новичку за переход по ссылке

LEVEL_REWARDS = {
    1: 3.0,  # Лига "Новичок" (0-5 друзей)
    2: 3.5,  # Лига "Продвинутый лев" (6-20 друзей)
    3: 4.5   # Лига "Мастер Stars" (21+ друзей)
}

# ==========================================
# 🗄️ ПОЛНАЯ БАЗА ДАННЫХ SQLite
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
                    daily_claimed_at TEXT DEFAULT NULL,
                    click_balance REAL DEFAULT 0.0,
                    energy INTEGER DEFAULT 100,
                    last_click_at TEXT DEFAULT NULL,
                    user_level INTEGER DEFAULT 1,
                    passive_speed REAL DEFAULT 0.0,
                    last_passive_collect TEXT DEFAULT NULL
                )
            ''')
            conn.commit()

    def get_user(self, user_id: int) -> Optional[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()

    def add_user(self, user_id: int, username: str, first_name: str, referrer_id: Optional[int] = None) -> Tuple[bool, Optional[int], float]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if cursor.fetchone() is not None:
                return False, None, 0.0

            valid_referrer = None
            reward = 0.0
            initial_balance = 0.0

            if referrer_id and referrer_id != user_id:
                cursor.execute('SELECT user_level FROM users WHERE user_id = ?', (referrer_id,))
                ref_data = cursor.fetchone()
                if ref_data:
                    valid_referrer = referrer_id
                    ref_level = ref_data[0]
                    reward = LEVEL_REWARDS.get(ref_level, 3.0)
                    initial_balance = REFERRAL_WELCOME_BONUS

            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, balance, referrer_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, initial_balance, valid_referrer))

            if valid_referrer:
                cursor.execute('''
                    UPDATE users 
                    SET balance = balance + ?, 
                        invited_count = invited_count + 1, 
                        activated_count = activated_count + 1
                    WHERE user_id = ?
                ''', (reward, valid_referrer))
                
                cursor.execute('SELECT activated_count, user_level FROM users WHERE user_id = ?', (valid_referrer,))
                act_count, current_lvl = cursor.fetchone()
                
                new_lvl = current_lvl
                if act_count > 20:
                    new_lvl = 3
                elif act_count > 5:
                    new_lvl = 2
                    
                if new_lvl != current_lvl:
                    cursor.execute('UPDATE users SET user_level = ? WHERE user_id = ?', (new_lvl, valid_referrer))

            conn.commit()
            return True, valid_referrer, reward

    def claim_daily(self, user_id: int) -> Tuple[bool, float]:
        now = datetime.datetime.now().date().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT daily_claimed_at FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0] == now:
                return False, 0.0
            
            reward = 0.10
            cursor.execute('UPDATE users SET balance = balance + ?, daily_claimed_at = ? WHERE user_id = ?', (reward, now, user_id))
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
            cursor.execute('SELECT username, first_name, activated_count FROM users ORDER BY activated_count DESC, balance DESC LIMIT ?', (limit,))
            return cursor.fetchall()

    def get_clicker_data(self, user_id: int) -> tuple:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT energy, click_balance, last_click_at FROM users WHERE user_id = ?', (user_id,))
            res = cursor.fetchone()
            if not res:
                return 100, 0.0, None
            
            energy, click_balance, last_click_at = res
            if last_click_at is None:
                return energy, click_balance, last_click_at
            
            passed_time = int(time.time()) - int(last_click_at)
            gained_energy = passed_time // 60
            
            if gained_energy > 0:
                energy = min(100, energy + gained_energy)
                cursor.execute('UPDATE users SET energy = ?, last_click_at = ? WHERE user_id = ?', (energy, int(time.time()), user_id))
                conn.commit()
                
            return energy, click_balance, last_click_at

    def save_click(self, user_id: int, new_energy: int, new_click_balance: float):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET energy = ?, click_balance = ?, last_click_at = ? WHERE user_id = ?', (new_energy, new_click_balance, int(time.time()), user_id))
            conn.commit()

    def transfer_click_balance(self, user_id: int) -> Tuple[bool, float]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT click_balance FROM users WHERE user_id = ?', (user_id,))
            res = cursor.fetchone()
            if res and res[0] >= 1.0:
                amount = res[0]
                cursor.execute('UPDATE users SET balance = balance + ?, click_balance = 0.0 WHERE user_id = ?', (amount, user_id))
                conn.commit()
                return True, amount
            return False, 0.0

    def upgrade_passive(self, user_id: int, cost: float = 10.0, speed_increase: float = 0.02) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT balance, passive_speed FROM users WHERE user_id = ?', (user_id,))
            res = cursor.fetchone()
            if res and res[0] >= cost:
                cursor.execute('UPDATE users SET balance = balance - ?, passive_speed = passive_speed + ?, last_passive_collect = COALESCE(last_passive_collect, ?) WHERE user_id = ?', (cost, speed_increase, int(time.time()), user_id))
                conn.commit()
                return True
            return False

    def collect_passive_income(self, user_id: int) -> Tuple[float, float]:
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT passive_speed, last_passive_collect FROM users WHERE user_id = ?', (user_id,))
            res = cursor.fetchone()
            
            if not res or res[0] == 0.0 or res[1] is None:
                return 0.0, (res[0] if res else 0.0)
                
            speed_per_hour = res[0]
            last_collect = int(res[1])
            
            seconds_passed = now - last_collect
            hours_passed = seconds_passed / 3600.0
            earnings = hours_passed * speed_per_hour
            
            if earnings > 0:
                cursor.execute('UPDATE users SET balance = balance + ?, last_passive_collect = ? WHERE user_id = ?', (earnings, now, user_id))
                conn.commit()
                
            return earnings, speed_per_hour

    def get_admin_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(user_id), SUM(balance) FROM users')
            total_users, total_balance = cursor.fetchone()
            return {"total_users": total_users or 0, "total_balance": total_balance or 0.0}

db = Database(DB_NAME)
dp = Dispatcher()
bot = Bot(token=BOT_TOKEN)
