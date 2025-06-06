import os
import logging
import sqlite3
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_TYPE = os.getenv("DB_TYPE", "sqlite")
DB_PATH = os.path.join(BASE_DIR, "scripts_status.db")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "uploader"),
    "password": os.getenv("MYSQL_PASSWORD", "uploader"),
    "database": os.getenv("MYSQL_DATABASE", "avito")
}

def connect_to_db():
    if DB_TYPE == "mysql":
        try:
            return mysql.connector.connect(**MYSQL_CONFIG)
        except mysql.connector.Error as err:
            logging.error(f"Ошибка подключения к MySQL: {err}. Используем SQLite.")
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = connect_to_db()
    cursor = conn.cursor()
    if DB_TYPE == "mysql":
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                name VARCHAR(255) PRIMARY KEY,
                value TEXT
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                name TEXT PRIMARY KEY,
                value TEXT
            )
        """)
    conn.commit()
    cursor.close()
    conn.close()

def set_config(name, value):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        if DB_TYPE == "mysql":
            query = """
                INSERT INTO config (name, value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE value = VALUES(value)
            """
        else:
            query = """
                INSERT INTO config (name, value)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET value=excluded.value
            """
        cursor.execute(query, (name, value))
        conn.commit()
        logging.info(f"Параметр config['{name}'] установлен в '{value}'")
    except Exception as e:
        logging.error(f"Ошибка при записи параметра config['{name}']: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_config(name):
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        query = "SELECT value FROM config WHERE name = %s" if DB_TYPE == "mysql" else "SELECT value FROM config WHERE name = ?"
        cursor.execute(query, (name,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logging.error(f"Ошибка при чтении config['{name}']: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def set_script_start(script_name):
    now = datetime.now().isoformat()
    set_config(f"{script_name}.start_time", now)
    set_config(f"{script_name}.status", "running")
    set_config(f"{script_name}.end_time", "")

def set_script_end(script_name, status="done"):
    now = datetime.now().isoformat()
    set_config(f"{script_name}.end_time", now)
    set_config(f"{script_name}.status", status)

def get_script_info(script_name: str) -> dict:
    try:
        start = get_config(f"{script_name}.start_time")
        end = get_config(f"{script_name}.end_time")
        status = get_config(f"{script_name}.status")

        duration = None
        if start:
            try:
                start_dt = datetime.fromisoformat(start)
                if status == "running" or not end:
                    end_dt = datetime.now()
                    end = None  # Скрипт еще выполняется, конец неизвестен
                else:
                    end_dt = datetime.fromisoformat(end)
                duration = (end_dt - start_dt).total_seconds()
            except Exception as e:
                logging.warning(f"Ошибка вычисления длительности для {script_name}: {e}")

        return {
            "start_time": start,
            "end_time": end,
            "status": status,
            "duration": duration
        }
    except Exception as e:
        logging.error(f"Ошибка при получении информации о скрипте '{script_name}': {e}")
        return {
            "start_time": None,
            "end_time": None,
            "status": None,
            "duration": None
        }
    
def get_all_configs_like(pattern: str):
    """
    Получает все пары (ключ, значение) из таблицы config, где имя соответствует шаблону.
    Шаблон должен использовать SQL-совместимые подстановки: % для любого количества символов.
    """
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        if DB_TYPE == "mysql":
            query = "SELECT name, value FROM config WHERE name LIKE %s"
        else:
            query = "SELECT name, value FROM config WHERE name LIKE ?"
        cursor.execute(query, (pattern,))
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"Ошибка при получении параметров по шаблону '{pattern}': {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def delete_config_key(key: str):
    """
    Удаляет запись из таблицы config по имени ключа.
    """
    conn = connect_to_db()
    cursor = conn.cursor()
    try:
        query = "DELETE FROM config WHERE name = %s" if DB_TYPE == "mysql" else "DELETE FROM config WHERE name = ?"
        cursor.execute(query, (key,))
        conn.commit()
        logging.info(f"Параметр config['{key}'] удалён")
    except Exception as e:
        logging.error(f"Ошибка при удалении config['{key}']: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
