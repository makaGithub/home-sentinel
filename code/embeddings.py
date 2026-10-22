# embeddings.py
"""
Загрузка и кэширование векторных представлений лиц из Immich.
Хранение по отдельным файлам для каждого человека.
"""

from __future__ import annotations

import json
import os
import pickle

import config
from database import fetch_embeddings_from_db
from utils import ensure_dirs, log

# Папка для хранения данных по людям
FACES_CACHE_DIR = os.path.join(config.CACHE_DIR, "faces")


def load_or_refresh_cache(force_refresh: bool = False, *, allow_db: bool = True):
    """
    Загружает векторные представления из кэша, либо при необходимости — из базы Immich.
    allow_db=False: только файловый кэш (для hs-gpu-helper).
    """
    ensure_dirs()
    os.makedirs(FACES_CACHE_DIR, exist_ok=True)

    index_path = os.path.join(FACES_CACHE_DIR, "index.json")
    cache_exists = os.path.exists(index_path)

    if cache_exists and not force_refresh:
        return _load_from_files()

    if not allow_db:
        if cache_exists:
            return _load_from_files()
        log("⚠️ Кэш лиц пуст, Immich на helper отключён — лиц пока нет")
        return [], [], [], []

    # Загружаем из БД
    log("📦 Загрузка базы лиц из Immich (из БД)...")
    all_embs_list, names, ids, all_confidences_list = fetch_embeddings_from_db()

    _save_to_files(all_embs_list, names, ids, all_confidences_list)

    log(f"✅ База лиц загружена ({len(all_embs_list)} человек)")
    return all_embs_list, names, ids, all_confidences_list


def load_faces_db_or_cache():
    """
    Для home-sentinel: пробует Immich DB, при ошибке — последний локальный кэш.
    При успехе из БД обновляет кэш на диске.
    """
    try:
        return load_or_refresh_cache(force_refresh=True, allow_db=True), "immich"
    except Exception as e:
        log(f"⚠️ Immich недоступна ({e}), беру последний кэш лиц...")
        index_path = os.path.join(FACES_CACHE_DIR, "index.json")
        if not os.path.exists(index_path):
            raise RuntimeError(
                "Immich недоступна и локальный кэш лиц пуст"
            ) from e
        return load_or_refresh_cache(force_refresh=False, allow_db=False), "cache"


def faces_to_pickle_blob(
    all_embs_list: list, names: list, ids: list, all_confidences_list: list
) -> bytes:
    """Сериализация для POST /v1/faces."""
    return pickle.dumps(
        {
            "ids": ids,
            "names": names,
            "embeddings": all_embs_list,
            "confidences": all_confidences_list,
        },
        protocol=pickle.HIGHEST_PROTOCOL,
    )


def faces_from_pickle_blob(blob: bytes):
    data = pickle.loads(blob)
    return (
        data["embeddings"],
        data["names"],
        data["ids"],
        data["confidences"],
    )


def save_faces_cache(
    all_embs_list: list, names: list, ids: list, all_confidences_list: list
) -> None:
    ensure_dirs()
    _save_to_files(all_embs_list, names, ids, all_confidences_list)


def _load_from_files():
    """Загружает данные из отдельных файлов для каждого человека."""
    log("📦 Загрузка векторных представлений лиц из кэша...")

    index_path = os.path.join(FACES_CACHE_DIR, "index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    all_embs_list = []
    names = []
    ids = []
    all_confidences_list = []
    loaded_names = []

    for entry in index:
        person_id = entry["id"]
        name = entry["name"]

        person_file = os.path.join(FACES_CACHE_DIR, f"{person_id}.pkl")

        with open(person_file, "rb") as f:
            person_data = pickle.load(f)

        all_embs_list.append(person_data["embeddings"])
        names.append(name)
        ids.append(person_id)
        all_confidences_list.append(person_data["confidences"])
        loaded_names.append(f"{name}({len(person_data['embeddings'])})")

    log(f"✅ База лиц загружена ({len(all_embs_list)} человек)")

    names_per_line = 5
    for i in range(0, len(loaded_names), names_per_line):
        chunk = loaded_names[i : i + names_per_line]
        log(f"   👥 {', '.join(chunk)}")

    return all_embs_list, names, ids, all_confidences_list


def _save_to_files(
    all_embs_list: list, names: list, ids: list, all_confidences_list: list
):
    """Сохраняет данные в отдельные файлы для каждого человека."""
    os.makedirs(FACES_CACHE_DIR, exist_ok=True)

    index = []
    for person_id, name in zip(ids, names):
        index.append({"id": str(person_id), "name": name})

    index_path = os.path.join(FACES_CACHE_DIR, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    for person_id, embs, confs in zip(ids, all_embs_list, all_confidences_list):
        person_data = {
            "embeddings": embs,
            "confidences": confs,
        }
        person_file = os.path.join(FACES_CACHE_DIR, f"{person_id}.pkl")
        with open(person_file, "wb") as f:
            pickle.dump(person_data, f, protocol=pickle.HIGHEST_PROTOCOL)
