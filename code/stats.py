# stats.py
"""
Статистика home-sentinel:
- запись распознанных лиц
- запись распознанных звуков
в отдельную БД home-sentinel (VISION_DB_NAME)
"""

import psycopg2

from config import DB_CONFIG, VISION_DB_NAME
from utils import log


def _conn():
    """Подключение к базе статистики home-sentinel."""
    cfg = DB_CONFIG.copy()
    cfg["dbname"] = VISION_DB_NAME
    return psycopg2.connect(**cfg)


def init_tables():
    """Создаёт таблицы статистики, если их ещё нет."""
    try:
        conn = _conn()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS person_stats (
                id SERIAL PRIMARY KEY,
                person_name TEXT NOT NULL,
                seen_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sound_stats (
                id SERIAL PRIMARY KEY,
                sound_name TEXT NOT NULL,
                detected_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log(f"⚠️ Ошибка инициализации таблиц статистики: {e}")


def record_person_seen(name: str):
    """Записывает факт появления человека."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO person_stats (person_name, seen_at) VALUES (%s, NOW())",
            (name,),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log(f"⚠️ Ошибка записи person_stats: {e}")


def record_sound_detected(sound: str):
    """Записывает факт обнаружения звука."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sound_stats (sound_name, detected_at) VALUES (%s, NOW())",
            (sound,),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log(f"⚠️ Ошибка записи sound_stats: {e}")
