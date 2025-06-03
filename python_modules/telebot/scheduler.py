import os
import sqlite3
from datetime import datetime
from croniter import croniter
from typing import List, Optional

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts_status.db"))

# === Инициализация таблицы расписания ===
def init_schedule_table():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS script_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_name TEXT NOT NULL,
                cron_expr TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                one_time INTEGER DEFAULT 0,
                last_run TEXT,
                UNIQUE(script_name, cron_expr)
            )
        """)
        conn.commit()

# === Добавление новой задачи ===
def add_schedule(script_name: str, cron_expr: str, one_time: bool = False):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR IGNORE INTO script_schedule (script_name, cron_expr, enabled, one_time, last_run)
            VALUES (?, ?, 1, ?, NULL)
        """, (script_name, cron_expr, int(one_time)))
        conn.commit()

# === Получение всех расписаний ===
def get_all_schedules(script_name: Optional[str] = None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if script_name:
            c.execute("SELECT * FROM script_schedule WHERE script_name = ?", (script_name,))
        else:
            c.execute("SELECT * FROM script_schedule")
        return c.fetchall()

# === Проверка: какие задачи пора запускать ===
def get_due_schedules(now: datetime) -> List[dict]:
    due = []
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT id, script_name, cron_expr, one_time, last_run FROM script_schedule WHERE enabled = 1")
        rows = c.fetchall()

    for row in rows:
        id_, name, expr, one_time, last_run = row
        base_time = datetime.fromisoformat(last_run) if last_run else now.replace(second=0, microsecond=0)
        cron = croniter(expr, base_time)
        next_time = cron.get_next(datetime)
        if now >= next_time:
            due.append({
                "id": id_,
                "script_name": name,
                "cron_expr": expr,
                "one_time": bool(one_time),
            })
    return due

# === Обновление времени последнего запуска ===
def mark_as_run(schedule_id: int, now: datetime):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("UPDATE script_schedule SET last_run = ? WHERE id = ?", (now.isoformat(), schedule_id))
        conn.commit()

# === Удаление (если one_time) ===
def remove_schedule(schedule_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM script_schedule WHERE id = ?", (schedule_id,))
        conn.commit()

# === Очистка и тест ===
if __name__ == "__main__":
    init_schedule_table()
    add_schedule("avito", "*/1 * * * *")  # Каждую минуту
    from pprint import pprint
    pprint(get_all_schedules())
    now = datetime.now()
    pprint(get_due_schedules(now))
