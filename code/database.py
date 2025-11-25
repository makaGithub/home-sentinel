# database.py
"""
Работа с PostgreSQL Immich: вытаскивание векторных представлений и confidence.
"""

import json
import time

import numpy as np
import psycopg2

import config
from utils import log, _l2_normalize


def fetch_embeddings_from_db():
    """
    Грузит векторные представления из Immich:
    - p.id, p.name, fs.embedding, af.confidence (если доступно)
    - группирует по personId
    - нормализует каждое векторное представление
    Возвращает:
        all_embs_list: List[List[np.ndarray]]
        names: List[str]
        ids: List[int]
        all_confidences_list: List[List[float]]
    """
    start_time = time.time()
    log("📡 Подключаюсь к базе Immich...")
    log(
        f"   Host: {config.DB_CONFIG['host']}:{config.DB_CONFIG['port']}, "
        f"DB: {config.DB_CONFIG['dbname']}, User: {config.DB_CONFIG['user']}"
    )

    try:
        conn_start = time.time()
        conn = psycopg2.connect(**config.DB_CONFIG, connect_timeout=10)
        conn_time = time.time() - conn_start
        log(f"✅ Подключение к базе установлено (заняло {conn_time:.2f} сек)")
    except psycopg2.OperationalError as e:
        log(f"❌ Ошибка подключения к базе: {e}")
        raise
    except Exception as e:
        log(f"❌ Неожиданная ошибка при подключении: {e}")
        raise

    cur = conn.cursor()
    log("📊 Выполняю запрос к базе данных...")

    # Пытаемся получить confidence, если доступно
    try:
        log("   Пробую запрос с confidence...")
        query_start = time.time()
        cur.execute(
            """
            SELECT p.id, p.name, fs.embedding, af.confidence
            FROM person p
            JOIN asset_face af ON af."personId" = p.id
            JOIN face_search fs ON fs."faceId" = af.id
            WHERE p.name IS NOT NULL AND TRIM(p.name) <> ''
            ORDER BY p.id, af.confidence DESC NULLS LAST;
        """
        )
        query_time = time.time() - query_start
        has_confidence = True
        log(f"✅ Запрос с confidence выполнен успешно (заняло {query_time:.2f} сек)")
    except Exception as e:
        log(
            f"   ⚠️ Confidence недоступен ({type(e).__name__}), "
            f"использую запрос без confidence..."
        )
        conn.rollback()
        query_start = time.time()
        cur.execute(
            """
            SELECT p.id, p.name, fs.embedding
            FROM person p
            JOIN asset_face af ON af."personId" = p.id
            JOIN face_search fs ON fs."faceId" = af.id
            WHERE p.name IS NOT NULL AND TRIM(p.name) <> ''
            ORDER BY p.id;
        """
        )
        query_time = time.time() - query_start
        has_confidence = False
        log(f"✅ Запрос без confidence выполнен успешно (заняло {query_time:.2f} сек)")

    log("📥 Получаю результаты запроса...")
    fetch_start = time.time()
    rows = cur.fetchall()
    fetch_time = time.time() - fetch_start
    log(f"✅ Получено {len(rows)} строк из базы данных (заняло {fetch_time:.2f} сек)")

    cur.close()
    conn.close()
    log("✅ Соединение с базой закрыто")

    log("🔄 Обрабатываю результаты...")
    by_id = {}
    processed = 0
    total = len(rows)
    log_interval = max(1, total // 10) if total > 0 else 1

    for row in rows:
        processed += 1
        if processed % log_interval == 0 or processed == total:
            pct = processed * 100 // total if total > 0 else 0
            log(f"   Обработано {processed}/{total} строк ({pct}%)")

        if has_confidence:
            pid, pname, emb, confidence = row
        else:
            pid, pname, emb = row
            confidence = None

        if not pname or emb is None:
            continue

        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                emb = [float(x) for x in emb.strip("[] ").split(",") if x.strip()]

        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim != 1:
            continue

        rec = by_id.setdefault(
            pid, {"name": pname.strip(), "embs": [], "confidences": []}
        )
        rec["embs"].append(emb)
        if confidence is not None:
            rec["confidences"].append(confidence)

    log(f"✅ Обработка завершена. Найдено {len(by_id)} уникальных персон")

    log("📦 Формирую финальные списки векторных представлений...")
    ids, names, all_embs_list = [], [], []
    all_confidences_list = []

    for pid, rec in by_id.items():
        ids.append(pid)
        names.append(rec["name"])

        normalized_embs = [_l2_normalize(emb) for emb in rec["embs"]]
        all_embs_list.append(normalized_embs)

        if rec["confidences"] and len(rec["confidences"]) == len(normalized_embs):
            all_confidences_list.append(rec["confidences"])
        else:
            all_confidences_list.append([1.0] * len(normalized_embs))

    log(f"✅ Загружено {len(ids)} лиц из Immich:")
    for pid, name, embs_list, confs_list in zip(
        ids, names, all_embs_list, all_confidences_list
    ):
        avg_conf = sum(confs_list) / len(confs_list) if confs_list else 0.0
        log(f"   - {pid:<4} | {name} ({len(embs_list)} векторов, avg confidence={avg_conf:.2f})")

    total_time = time.time() - start_time
    log(f"✅ Загрузка из базы завершена за {total_time:.2f} сек")

    return all_embs_list, names, ids, all_confidences_list
