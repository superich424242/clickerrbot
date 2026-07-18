import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
import aiosqlite
import os

# ---------- КОНФИГУРАЦИЯ ----------
BOT_TOKEN = os.getenv("8981424648:AAFDSu9LVH9DQTKqDIsjQ_6zZquDwtaWjb0")  # читаем из переменных окружения
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

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
            # Новый пользователь
            await db.execute(
                "INSERT INTO users (user_id) VALUES (?)",
                (user_id,)
            )
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
            await db.execute(
                f"UPDATE users SET {key} = ? WHERE user_id = ?",
                (value, user_id)
            )
        await db.commit()

async def get_top_users(limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, score FROM users ORDER BY score DESC LIMIT ?",
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return rows

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def get_auto_multiplier(total_clicks: int) -> int:
    if total_clicks >= 10000:
        return 10
    elif total_clicks >= 5000:
        return 5
    elif total_clicks >= 1000:
        return 2
    else:
        return 1

def get_status_name(multiplier: int) -> str:
    map_status = {
        10: "👑 ULTRA (x10)",
        5: "⭐ GOLD (x5)",
        2: "💎 PREMIUM (x2)",
        1: "🟢 Обычный (x1)",
    }
    return map_status.get(multiplier, "🟢 Обычный (x1)")

def get_farm_price(level: int) -> int:
    return 200 + 50 * level

def get_next_status_info(user: dict) -> str:
    bought = user["bought_multiplier"]
    clicks = user["total_clicks"]
    if bought < 2:
        return "Купите PREMIUM (x2) за 1000 монет"
    if bought < 5:
        return "Купите GOLD (x5) за 5000 монет"
    if bought < 10:
        return "Купите ULTRA (x10) за 10000 монет"
    if clicks < 10000:
        return f"До автоматического ULTRA: {10000 - clicks} кликов"
    return "🎉 Все статусы получены!"

def format_stats(user: dict) -> str:
    auto = get_auto_multiplier(user["total_clicks"])
    bought = user["bought_multiplier"]
    final_mult = max(auto, bought)
    status = get_status_name(final_mult)
    farm_price = get_farm_price(user["farm_level"])
    next_info = get_next_status_info(user)
    return (
        f"💰 Монет: **{user['score']}**\n"
        f"🐣 Всего кликов: **{user['total_clicks']}**\n"
        f"💪 Сила клика: **{user['click_power']}** × {final_mult} = **{user['click_power'] * final_mult}**\n"
        f"🚜 Уровень фермы: **{user['farm_level']}** (доход: {user['farm_level']} монет/сек)\n"
        f"🏅 Текущий статус: {status}\n"
        f"📈 {next_info}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Цена следующей фермы: **{farm_price}** монет"
    )

# ---------- КЛАВИАТУРЫ ----------
def get_main_keyboard(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🐣 КЛИК (1 сек)", callback_data="click"))
    farm_price = get_farm_price(user["farm_level"])
    builder.row(
        InlineKeyboardButton(
            text=f"🚜 Купить ферму (ур. {user['farm_level']}) — {farm_price} монет",
            callback_data="buy_farm"
        )
    )
    builder.row(InlineKeyboardButton(text="🏪 Магазин статусов", callback_data="shop"))
    builder.row(InlineKeyboardButton(text="📊 Топ 10", callback_data="top"))
    builder.row(InlineKeyboardButton(text="🔄 Сброс", callback_data="reset"))
    return builder.as_markup()

def get_shop_keyboard(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    bought = user["bought_multiplier"]
    if bought < 2:
        builder.row(InlineKeyboardButton(text="💎 PREMIUM (x2) — 1000 монет", callback_data="buy_status_2"))
    if bought < 5:
        builder.row(InlineKeyboardButton(text="⭐ GOLD (x5) — 5000 монет", callback_data="buy_status_5"))
    if bought < 10:
        builder.row(InlineKeyboardButton(text="👑 ULTRA (x10) — 10000 монет", callback_data="buy_status_10"))
    if bought >= 10:
        builder.row(InlineKeyboardButton(text="✅ Все статусы куплены!", callback_data="noop"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main"))
    return builder.as_markup()

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    text = f"🐔 **Добро пожаловать в кликер!**\nКликай каждую секунду, зарабатывай монеты, покупай ферму и статусы!\n\n{format_stats(user)}"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(user))

@dp.callback_query(lambda c: c.data == "click")
async def handle_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)

    now = int(time.time())
    if now - user["last_click_time"] < 1:
        await callback.answer("⏳ Подожди 1 секунду!", show_alert=True)
        return

    await update_user(user_id, last_click_time=now)

    auto = get_auto_multiplier(user["total_clicks"])
    bought = user["bought_multiplier"]
    final_mult = max(auto, bought)
    gain = user["click_power"] * final_mult
    new_score = user["score"] + gain
    new_clicks = user["total_clicks"] + 1

    await update_user(user_id, score=new_score, total_clicks=new_clicks)
    user = await get_user(user_id)  # обновляем данные

    try:
        await callback.message.edit_text(
            format_stats(user),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user)
        )
    except TelegramBadRequest:
        pass
    await callback.answer(f"+{gain} монет!")

@dp.callback_query(lambda c: c.data == "buy_farm")
async def handle_buy_farm(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    price = get_farm_price(user["farm_level"])

    if user["score"] < price:
        await callback.answer(f"❌ Нужно {price} монет!", show_alert=True)
        return

    new_score = user["score"] - price
    new_farm = user["farm_level"] + 1
    await update_user(user_id, score=new_score, farm_level=new_farm)
    user = await get_user(user_id)

    try:
        await callback.message.edit_text(
            format_stats(user),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user)
        )
    except TelegramBadRequest:
        pass
    await callback.answer("🚜 Ферма улучшена! +1 монета/сек")

@dp.callback_query(lambda c: c.data == "shop")
async def handle_shop(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    text = (
        "🏪 **Магазин статусов**\n\n"
        "Купите постоянный множитель к силе клика:\n"
        "• 💎 PREMIUM (x2) — 1000 монет\n"
        "• ⭐ GOLD (x5) — 5000 монет\n"
        "• 👑 ULTRA (x10) — 10000 монет\n\n"
        f"У вас сейчас: {user['bought_multiplier']}x\n"
        f"Монет: {user['score']}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_shop_keyboard(user)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("buy_status_"))
async def handle_buy_status(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)

    target_mult = int(callback.data.split("_")[2])  # 2, 5, 10
    price_map = {2: 1000, 5: 5000, 10: 10000}
    price = price_map[target_mult]

    if user["bought_multiplier"] >= target_mult:
        await callback.answer("У вас уже есть этот или более высокий статус!", show_alert=True)
        return
    if user["score"] < price:
        await callback.answer(f"❌ Нужно {price} монет!", show_alert=True)
        return

    new_score = user["score"] - price
    await update_user(user_id, score=new_score, bought_multiplier=target_mult)
    user = await get_user(user_id)

    try:
        await callback.message.edit_text(
            format_stats(user),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user)
        )
    except TelegramBadRequest:
        pass
    await callback.answer(f"✅ Статус {target_mult}x куплен!")

@dp.callback_query(lambda c: c.data == "back_to_main")
async def handle_back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    try:
        await callback.message.edit_text(
            format_stats(user),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user)
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

@dp.callback_query(lambda c: c.data == "top")
async def handle_top(callback: types.CallbackQuery):
    top = await get_top_users(10)
    if not top:
        await callback.answer("Пока нет игроков.", show_alert=True)
        return

    text = "🏆 **Топ 10 игроков**\n\n"
    for i, (user_id, score) in enumerate(top, 1):
        try:
            user = await bot.get_chat(user_id)
            name = user.full_name or str(user_id)
        except:
            name = str(user_id)
        text += f"{i}. {name} — {score} 🪙\n"
    await callback.answer(text, show_alert=True)

@dp.callback_query(lambda c: c.data == "reset")
async def handle_reset(callback: types.CallbackQuery):
    user_id = callback.from_user.id
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
    try:
        await callback.message.edit_text(
            format_stats(user),
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user)
        )
    except TelegramBadRequest:
        pass
    await callback.answer("🔄 Прогресс сброшен!", show_alert=True)

@dp.callback_query(lambda c: c.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()

# ---------- ФОНОВАЯ ЗАДАЧА: ДОХОД С ФЕРМЫ ----------
async def farm_loop():
    while True:
        await asyncio.sleep(1)
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET score = score + farm_level WHERE farm_level > 0"
                )
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
