import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, Text
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest
import aiosqlite
import os

# ---------- КОНФИГУРАЦИЯ ----------
BOT_TOKEN = "8981424648:AAFDSu9LVH9DQTKqDIsjQ_6zZquDwtaWjb0"  # ⬅️ вставь свой токен
DB_PATH = "clicker.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- РАБОТА С БД ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                score INTEGER DEFAULT 0,
                total_clicks INTEGER DEFAULT 0,
                click_power INTEGER DEFAULT 1,
                farm_level INTEGER DEFAULT 0,
                last_click_time INTEGER DEFAULT 0,
                bought_multiplier INTEGER DEFAULT 1
            )
        """)
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT score, total_clicks, click_power, farm_level, last_click_time, bought_multiplier FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "score": row[0],
                    "total_clicks": row[1],
                    "click_power": row[2],
                    "farm_level": row[3],
                    "last_click_time": row[4],
                    "bought_multiplier": row[5],
                }
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            return {
                "score": 0,
                "total_clicks": 0,
                "click_power": 1,
                "farm_level": 0,
                "last_click_time": 0,
                "bought_multiplier": 1,
            }

async def update_user(user_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in kwargs.items():
            await db.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

async def get_top_users(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, score FROM users ORDER BY score DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_auto_multiplier(total_clicks: int) -> int:
    if total_clicks >= 10000: return 10
    if total_clicks >= 5000: return 5
    if total_clicks >= 1000: return 2
    return 1

def get_status_name(multiplier: int) -> str:
    return {10: "👑 ULTRA (x10)", 5: "⭐ GOLD (x5)", 2: "💎 PREMIUM (x2)", 1: "🟢 Обычный (x1)"}.get(multiplier, "🟢 Обычный (x1)")

def get_farm_price(level: int) -> int:
    return 200 + 50 * level

def get_next_status_info(user: dict) -> str:
    bought = user["bought_multiplier"]
    clicks = user["total_clicks"]
    if bought < 2: return "Купите PREMIUM (x2) за 1000 монет"
    if bought < 5: return "Купите GOLD (x5) за 5000 монет"
    if bought < 10: return "Купите ULTRA (x10) за 10000 монет"
    if clicks < 10000: return f"До автоматического ULTRA: {10000 - clicks} кликов"
    return "🎉 Все статусы получены!"

def format_stats(user: dict) -> str:
    final_mult = max(get_auto_multiplier(user["total_clicks"]), user["bought_multiplier"])
    return (
        f"💰 Монет: **{user['score']}**\n"
        f"🐣 Всего кликов: **{user['total_clicks']}**\n"
        f"💪 Сила клика: **{user['click_power']}** × {final_mult} = **{user['click_power'] * final_mult}**\n"
        f"🚜 Уровень фермы: **{user['farm_level']}** (доход: {user['farm_level']} монет/сек)\n"
        f"🏅 Текущий статус: {get_status_name(final_mult)}\n"
        f"📈 {get_next_status_info(user)}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Цена следующей фермы: **{get_farm_price(user['farm_level'])}** монет"
    )

# ---------- КЛАВИАТУРА (reply) ----------
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🐣 КЛИК (1 сек)")],
            [KeyboardButton(text="🚜 Купить ферму")],
            [KeyboardButton(text="🏪 Магазин статусов")],
            [KeyboardButton(text="📊 Топ 10")],
            [KeyboardButton(text="🔄 Сброс")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = await get_user(message.from_user.id)
    await message.answer(
        f"🐔 **Добро пожаловать в кликер!**\nКликай каждую секунду, зарабатывай монеты, покупай ферму и статусы!\n\n{format_stats(user)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# Обработчик текстовых сообщений (все кнопки)
@dp.message(Text("🐣 КЛИК (1 сек)"))
async def handle_click(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    now = int(time.time())
    if now - user["last_click_time"] < 1:
        await message.answer("⏳ Подожди 1 секунду!")
        return
    await update_user(user_id, last_click_time=now)
    final_mult = max(get_auto_multiplier(user["total_clicks"]), user["bought_multiplier"])
    gain = user["click_power"] * final_mult
    new_score = user["score"] + gain
    new_clicks = user["total_clicks"] + 1
    await update_user(user_id, score=new_score, total_clicks=new_clicks)
    user = await get_user(user_id)
    await message.answer(
        f"✅ +{gain} монет!\n\n{format_stats(user)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(Text("🚜 Купить ферму"))
async def handle_buy_farm(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    price = get_farm_price(user["farm_level"])
    if user["score"] < price:
        await message.answer(f"❌ Нужно {price} монет!", reply_markup=get_main_keyboard())
        return
    new_score = user["score"] - price
    new_farm = user["farm_level"] + 1
    await update_user(user_id, score=new_score, farm_level=new_farm)
    user = await get_user(user_id)
    await message.answer(
        f"🚜 Ферма улучшена! +1 монета/сек\n\n{format_stats(user)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(Text("🏪 Магазин статусов"))
async def handle_shop(message: types.Message):
    user = await get_user(message.from_user.id)
    text = (
        "🏪 **Магазин статусов**\n\n"
        "Купите постоянный множитель к силе клика:\n"
        "• 💎 PREMIUM (x2) — 1000 монет\n"
        "• ⭐ GOLD (x5) — 5000 монет\n"
        "• 👑 ULTRA (x10) — 10000 монет\n\n"
        f"У вас сейчас: {user['bought_multiplier']}x\n"
        f"Монет: {user['score']}\n\n"
        "Напиши /buy_2, /buy_5 или /buy_10 для покупки."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# Покупка статусов через команды (можно и через кнопки, но проще так)
@dp.message(Command("buy_2"))
async def buy_status_2(message: types.Message):
    await buy_status(message, 2)

@dp.message(Command("buy_5"))
async def buy_status_5(message: types.Message):
    await buy_status(message, 5)

@dp.message(Command("buy_10"))
async def buy_status_10(message: types.Message):
    await buy_status(message, 10)

async def buy_status(message: types.Message, target_mult: int):
    user_id = message.from_user.id
    user = await get_user(user_id)
    price_map = {2: 1000, 5: 5000, 10: 10000}
    price = price_map[target_mult]
    if user["bought_multiplier"] >= target_mult:
        await message.answer("❌ У вас уже есть этот или более высокий статус!", reply_markup=get_main_keyboard())
        return
    if user["score"] < price:
        await message.answer(f"❌ Нужно {price} монет!", reply_markup=get_main_keyboard())
        return
    new_score = user["score"] - price
    await update_user(user_id, score=new_score, bought_multiplier=target_mult)
    user = await get_user(user_id)
    await message.answer(
        f"✅ Статус {target_mult}x куплен!\n\n{format_stats(user)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(Text("📊 Топ 10"))
async def handle_top(message: types.Message):
    top = await get_top_users(10)
    if not top:
        await message.answer("Пока нет игроков.", reply_markup=get_main_keyboard())
        return
    text = "🏆 **Топ 10 игроков**\n\n"
    for i, (user_id, score) in enumerate(top, 1):
        try:
            user = await bot.get_chat(user_id)
            name = user.full_name or str(user_id)
        except:
            name = str(user_id)
        text += f"{i}. {name} — {score} 🪙\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(Text("🔄 Сброс"))
async def handle_reset(message: types.Message):
    user_id = message.from_user.id
    await update_user(
        user_id,
        score=0,
        total_clicks=0,
        click_power=1,
        farm_level=0,
        last_click_time=0,
        bought_multiplier=1
    )
    user = await get_user(user_id)
    await message.answer(
        f"🔄 Прогресс сброшен!\n\n{format_stats(user)}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ---------- ФОНОВАЯ ЗАДАЧА: ДОХОД С ФЕРМЫ ----------
async def farm_loop():
    while True:
        await asyncio.sleep(1)
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET score = score + farm_level WHERE farm_level > 0")
                await db.commit()
        except Exception as e:
            logging.error(f"Ошибка фермы: {e}")

# ---------- ЗАПУСК ----------
async def main():
    await init_db()
    asyncio.create_task(farm_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
