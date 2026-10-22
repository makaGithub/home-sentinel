# database.py
"""
Работа с PostgreSQL Immich: вытаскивание векторных представлений лиц.
Схема Immich (personGroupId / person_group), не старый personId.
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
    - person."personGroupId", person.name, face_search.embedding
    - группирует по personGroupId
    - нормализует каждое векторное представление
    Возвращает:
        all_embs_list, names, ids, all_confidences_list
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

    query_start = time.time()
    # Immich: asset_face.personGroupId → person_group ← person.personGroupId
    cur.execute(
        """
        SELECT p."personGroupId", p.name, fs.embedding
        FROM person p
        JOIN asset_face af ON af."personGroupId" = p."personGroupId"
        JOIN face_search fs ON fs."faceId" = af.id
        WHERE TRIM(p.name) <> ''
          AND af."deletedAt" IS NULL
          AND af."isVisible" IS TRUE
        ORDER BY p."personGroupId";
        """
    )
    query_time = time.time() - query_start
    log(f"✅ Запрос выполнен успешно (заняло {query_time:.2f} сек)")

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

        pid, pname, emb = row

        if not pname or emb is None:
            continue

        emb = _parse_embedding(emb)
        if emb is None:
            continue

        pid_key = str(pid)
        rec = by_id.setdefault(pid_key, {"name": pname.strip(), "embs": []})
        rec["embs"].append(emb)

    log(f"✅ Обработка завершена. Найдено {len(by_id)} уникальных персон")

    log("📦 Формирую финальные списки векторных представлений...")
    ids, names, all_embs_list = [], [], []
    all_confidences_list = []

    for pid, rec in by_id.items():
        ids.append(pid)
        names.append(rec["name"])

        normalized_embs = [_l2_normalize(emb) for emb in rec["embs"]]
        all_embs_list.append(normalized_embs)
        all_confidences_list.append([1.0] * len(normalized_embs))

    log(f"✅ Загружено {len(ids)} лиц из Immich:")
    for pid, name, embs_list in zip(ids, names, all_embs_list):
        log(f"   - {str(pid)[:8]:<8} | {name} ({len(embs_list)} векторов)")

    total_time = time.time() - start_time
    log(f"✅ Загрузка из базы завершена за {total_time:.2f} сек")

    return all_embs_list, names, ids, all_confidences_list


def _parse_embedding(emb):
    if isinstance(emb, str):
        try:
            emb = json.loads(emb)
        except Exception:
            # pgvector text: [1.0,2.0,...]
            emb = [float(x) for x in emb.strip("[] ").split(",") if x.strip()]
    elif hasattr(emb, "tolist"):
        emb = emb.tolist()

    arr = np.asarray(emb, dtype=np.float32)
    if arr.ndim != 1 or arr.size == 0:
        return None
    return arr
