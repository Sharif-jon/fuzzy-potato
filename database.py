import sqlite3
from datetime import datetime

DB_NAME = "expenses.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                category TEXT,
                description TEXT,
                date TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS limits (
                user_id INTEGER PRIMARY KEY,
                daily_limit INTEGER
            )
        """)
        conn.commit()

def add_expense(user_id: int, amount: int, category: str, description: str):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""
            INSERT INTO expenses (user_id, amount, category, description, date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, category, description, now))
        conn.commit()

def get_expenses_by_period(user_id: int, start_date: str, end_date: str):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY date DESC
        """, (user_id, start_date, end_date))
        return c.fetchall()

def get_category_stats(user_id: int, start_date: str, end_date: str):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT category, SUM(amount)
            FROM expenses
            WHERE user_id = ? AND date BETWEEN ? AND ?
            GROUP BY category
        """, (user_id, start_date, end_date))
        return c.fetchall()

def get_all_expenses(user_id: int, start_date: str, end_date: str):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT amount, category, description, date
            FROM expenses
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY date DESC
        """, (user_id, start_date, end_date))
        return c.fetchall()

def set_daily_limit(user_id: int, limit: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("REPLACE INTO limits (user_id, daily_limit) VALUES (?, ?)", (user_id, limit))
        conn.commit()

def get_daily_limit(user_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT daily_limit FROM limits WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row[0] if row else None

def get_today_expense_sum(user_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d 00:00")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.execute("""
            SELECT SUM(amount) FROM expenses
            WHERE user_id = ? AND date BETWEEN ? AND ?
        """, (user_id, today, now))
        row = c.fetchone()
        return row[0] if row and row[0] else 0

    #7610405152:AAEnnntG4RbE_fxTU_E7b_955-z0y5G4DRw