# embeddings.py
"""
Загрузка и кэширование векторных представлений лиц из Immich.
Хранение по отдельным файлам для каждого человека.
"""

import json
import os
import pickle

import numpy as np

import config
from utils import ensure_dirs, _l2_normalize, log
from database import fetch_embeddings_from_db


# Папка для хранения данных по людям
FACES_CACHE_DIR = os.path.join(config.CACHE_DIR, "faces")


def load_or_refresh_cache(force_refresh: bool = False):
    """
    Загружает векторные представления из кэша, либо при необходимости — из базы Immich.
    Использует отдельные файлы для каждого человека.
    """
    ensure_dirs()
    os.makedirs(FACES_CACHE_DIR, exist_ok=True)

    index_path = os.path.join(FACES_CACHE_DIR, "index.json")
    cache_exists = os.path.exists(index_path)

    if cache_exists and not force_refresh:
        return _load_from_files()

    # Загружаем из БД
    log("📦 Загрузка базы лиц из Immich (из БД)...")
    all_embs_list, names, ids, all_confidences_list = fetch_embeddings_from_db()
    
    # Сохраняем в новый формат
    _save_to_files(all_embs_list, names, ids, all_confidences_list)

    log(f"✅ База лиц загружена ({len(all_embs_list)} человек)")
    return all_embs_list, names, ids, all_confidences_list


def _load_from_files():
    """Загружает данные из отдельных файлов для каждого человека."""
    log("📦 Загрузка векторных представлений лиц из Immich...")
    
    index_path = os.path.join(FACES_CACHE_DIR, "index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    
    all_embs_list = []
    names = []
    ids = []
    all_confidences_list = []
    loaded_names = []  # Для вывода в лог
    
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
    
    # Выводим имена по 5 на строку
    names_per_line = 5
    for i in range(0, len(loaded_names), names_per_line):
        chunk = loaded_names[i:i + names_per_line]
        log(f"   👥 {', '.join(chunk)}")
    
    return all_embs_list, names, ids, all_confidences_list


def _save_to_files(all_embs_list: list, names: list, ids: list, all_confidences_list: list):
    """Сохраняет данные в отдельные файлы для каждого человека."""
    os.makedirs(FACES_CACHE_DIR, exist_ok=True)
    
    # Создаём индекс
    index = []
    for person_id, name in zip(ids, names):
        index.append({"id": person_id, "name": name})
    
    index_path = os.path.join(FACES_CACHE_DIR, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    # Сохраняем данные каждого человека
    for person_id, embs, confs in zip(ids, all_embs_list, all_confidences_list):
        person_data = {
            "embeddings": embs,
            "confidences": confs,
        }
        person_file = os.path.join(FACES_CACHE_DIR, f"{person_id}.pkl")
        with open(person_file, "wb") as f:
            pickle.dump(person_data, f, protocol=pickle.HIGHEST_PROTOCOL)


