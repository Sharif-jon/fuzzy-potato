import asyncio
import sqlite3
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from datetime import datetime
from openpyxl import Workbook
from fastapi import FastAPI
import uvicorn
import os

TOKEN = os.getenv("TOKEN")
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

DB_NAME = "expenses.db"
LIMIT_FILE = "limit.txt"
app = FastAPI()


CATEGORY_ICONS = {
    "еда": "🍕",
    "транспорт": "🚌",
    "развлечения": "🎮",
    "одежда": "👕",
    "другое": "📦"
}

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить расход")],
        [KeyboardButton(text="📋 Показать расходы"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🚫 Установить лимит")], [KeyboardButton(text="📈 График")], 
        [KeyboardButton(text="📁 Экспорт в Excel")]
    ], resize_keyboard=True
)

CATEGORY_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="еда"), KeyboardButton(text="транспорт"), KeyboardButton(text="развлечения")],
        [KeyboardButton(text="одежда"), KeyboardButton(text="другое")]
    ], resize_keyboard=True
)

class ExpenseState(StatesGroup):
    amount = State()
    category = State()
    description = State()

class LimitState(StatesGroup):
    category = State()
    amount = State()

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount INTEGER,
                category TEXT,
                description TEXT,
                date TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS category_limits (
                category TEXT PRIMARY KEY,
                category_limit INTEGER
            )
        """)

def add_expense(amount, category, description):
    date = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            "INSERT INTO expenses (amount, category, description, date) VALUES (?, ?, ?, ?)",
            (amount, category, description, date)
        )

def get_expenses():
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute(
            "SELECT amount, category, description, date FROM expenses"
        ).fetchall()

def get_expense_stats():
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute(
            "SELECT category, SUM(amount) FROM expenses GROUP BY category"
        ).fetchall()

def get_total_expense():
    with sqlite3.connect(DB_NAME) as conn:
        result = conn.execute(
            "SELECT SUM(amount) FROM expenses"
        ).fetchone()
    return result[0] if result and result[0] else 0

def get_category_limit(category):
    with sqlite3.connect(DB_NAME) as conn:
        result = conn.execute(
            "SELECT category_limit FROM category_limits WHERE category=?", (category,)
        ).fetchone()
    return result[0] if result else None

def set_category_limit(category, limit):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO category_limits (category, category_limit) VALUES (?, ?)",
            (category, limit)
        )

def sum_by_category(category):
    with sqlite3.connect(DB_NAME) as conn:
        result = conn.execute(
            "SELECT SUM(amount) FROM expenses WHERE category=?", (category,)
        ).fetchone()
    return result[0] if result and result[0] else 0

@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "Добро пожаловать! Я помогу тебе управлять расходами.", reply_markup=MAIN_KB
    )

@dp.message(F.text == "➕ Добавить расход")
async def add_expense_start(message: Message, state: FSMContext):
    await state.set_state(ExpenseState.amount)
    await message.answer("Введите сумму:")

@dp.message(ExpenseState.amount)
async def set_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Нужно ввести число!")
        return
    await state.update_data(amount=int(message.text))
    await state.set_state(ExpenseState.category)
    await message.answer("Выберите категорию:", reply_markup=CATEGORY_KB)

@dp.message(ExpenseState.category)
async def set_category(message: Message, state: FSMContext):
    if message.text not in ["еда","транспорт","развлечения","одежда","другое"]:
        await message.answer("Пожалуйста, выбери категорию с клавиатуры!")
        return
    await state.update_data(category=message.text)
    await state.set_state(ExpenseState.description)
    await message.answer("Введите описание (или '-' для пропуска):")

@dp.message(ExpenseState.description)
async def set_description(message: Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    category = data['category']
    description = message.text if message.text != "-" else ""
    add_expense(amount, category, description)
    await state.clear()

    total_category = sum_by_category(category)
    limit = get_category_limit(category)
    warn_text = ""
    if limit and total_category > limit:
        warn_text = f"\n⚠️ Лимит для категории '{category}' превышен: {total_category}/{limit} сум!"
    await message.answer(
        f"✅ Расход {amount} сум добавлен в категорию '{category}'!{warn_text}",
        reply_markup=MAIN_KB
    )

@dp.message(Command("plan"))
async def plan(message: Message):
    total = get_total_expense()           # сколько уже потрачено
    # для демонстрации лимита по всем категориям используем сумму лимитов
    with sqlite3.connect(DB_NAME) as conn:
        result = conn.execute("SELECT SUM(category_limit) FROM category_limits").fetchone()
    overall_limit = result[0] if result and result[0] else 0

    if overall_limit == 0:
        await message.answer(
            "❗ Лимит пока не установлен.\nИспользуйте команду 🚫 Установить лимит для установки лимита."
        )
        return

    def make_progress_bar(current, limit, length=10):
        if limit <= 0:
            return "⚪" * length
        filled = int((current / limit) * length)
        if filled > length:
            filled = length
        return "🔵" * filled + "⚪" * (length - filled)

    progress = make_progress_bar(total, overall_limit)
    percent = (total / overall_limit) * 100

    await message.answer(
        f"<b>📊 Ваш лимит расходов</b>\n"
        f"{progress}\n"
        f"💸 Потрачено: {total}/{overall_limit} сум ({percent:.1f}%)",
        parse_mode="HTML"
    )

@dp.message(F.text == "🚫 Установить лимит")
async def set_limit_start(message: Message, state: FSMContext):
    await state.set_state(LimitState.category)
    await message.answer(
        "Для какой категории установить лимит?", reply_markup=CATEGORY_KB
    )

@dp.message(F.text == "📋 Показать расходы")
async def show_expenses(message: Message):
    data = get_expenses()
    if not data:
        await message.answer("ℹ️ Пока нет расходов.", reply_markup=MAIN_KB)
        return

    last = data[-10:]  # последние 10 расходов
    text = "<b>📋 Последние расходы:</b>\n"
    text += "——————————————————————\n"
    total = 0
    for amount, category, desc, date in last:
        icon = CATEGORY_ICONS.get(category, "💸")
        desc_text = desc if desc else "—"
        text += f"{icon} {amount:>7} сум | {category:<10} | {desc_text}\n"
        total += amount
    text += "——————————————————————\n"
    text += f"<b>💰 Сумма этих расходов:</b> {total} сум"
    await message.answer(text, parse_mode="HTML", reply_markup=MAIN_KB)

# =================== КРАСИВАЯ СТАТИСТИКА ПО КАТЕГОРИЯМ ===================
@dp.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message):
    stats = get_expense_stats()
    if not stats:
        await message.answer(
            "ℹ️ Нет данных для отображения статистики.",
            reply_markup=MAIN_KB
        )
        return

    total = sum([s[1] for s in stats])
    text = "<b>📊 Статистика по категориям:</b>\n"
    text += "——————————————————————\n"
    for cat, amt in stats:
        icon = CATEGORY_ICONS.get(cat, "💸")
        percent = (amt / total) * 100 if total > 0 else 0
        text += f"{icon} <b>{cat.capitalize():<10}</b> {amt:>7} сум ({percent:.1f}%)\n"
    text += "——————————————————————\n"
    text += f"<b>💰 Итого расходов:</b> {total} сум"
    await message.answer(text, parse_mode="HTML", reply_markup=MAIN_KB)

@dp.message(F.text == "📈 График")
async def cmd_chart(message: Message):
    stats = get_expense_stats()
    if not stats:
        await message.answer("Нет данных.")
        return
    categories, values = zip(*stats)
    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=categories, autopct='%1.1f%%')
    plt.title('Статистика расходов')
    plt.savefig("chart.png")
    await message.answer_photo(types.FSInputFile("chart.png"))
    os.remove("chart.png")


@dp.message(F.text == "📁 Экспорт в Excel")
async def cmd_export(message: Message):
    data = get_expenses()
    if not data:
        await message.answer("Нет данных.")
        return
    wb = Workbook()
    ws = wb.active
    ws.append(["Сумма", "Категория", "Описание", "Дата"])
    for row in data:
        ws.append(row)
    path = "expenses.xlsx"
    wb.save(path)
    await message.answer_document(types.FSInputFile(path))
    os.remove(path)

@dp.message(LimitState.category)
async def set_limit_category(message: Message, state: FSMContext):
    if message.text not in ["еда","транспорт","развлечения","одежда","другое"]:
        await message.answer("Пожалуйста, выбери категорию с клавиатуры!")
        return
    await state.update_data(category=message.text)
    await state.set_state(LimitState.amount)
    await message.answer(f"Введите лимит для '{message.text}' (сум):")

@dp.message(LimitState.amount)
async def set_limit_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Нужно ввести число!")
        return
    data = await state.get_data()
    set_category_limit(data['category'], int(message.text))
    await state.clear()
    await message.answer(
        f"✅ Лимит для '{data['category']}' установлен: {message.text} сум",
        reply_markup=MAIN_KB
    )

@app.get("/")
async def health_check():
    """This endpoint is just for Render's health check."""
    return {"status": "ok", "message": "Bot is running"}

# 2. Create an async function to run the web server
async def run_web_server():
    """Runs the Uvicorn web server."""
    # Render sets the PORT environment variable. Default to 10000 if not set.
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(
        app,
        host="0.0.0.0",  # Important: Binds to all interfaces
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

# 3. Create an async function to start your bot
async def run_bot():
    """Starts the bot polling."""
    await dp.start_polling(bot)

# 4. Create a main function to run both tasks at the same time
async def main():
    """Runs the bot and the web server concurrently."""
    await asyncio.gather(
        run_bot(),
        run_web_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot and server stopped.")


