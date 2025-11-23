# embeddings.py
"""
Загрузка и кэширование векторных представлений лиц из Immich.
"""

import json
import os

import numpy as np

import config
from utils import ensure_dirs, _l2_normalize, log
from database import fetch_embeddings_from_db


def load_or_refresh_cache(force_refresh: bool = False):
    """
    Загружает векторные представления из кэша, либо при необходимости — из базы Immich.
    Новый формат:
        - embeddings_list.json: список списков векторов
        - confidences_list.json: список списков confidence
    Параллельно поддерживает старый формат (embeddings.npy + names/ids.json).
    """
    ensure_dirs()

    embeddings_list_path = os.path.join(config.CACHE_DIR, "embeddings_list.json")
    confidences_list_path = os.path.join(config.CACHE_DIR, "confidences_list.json")

    cache_exists = (
        os.path.exists(embeddings_list_path)
        and os.path.exists(config.NAMES_PATH)
        and os.path.exists(config.IDS_PATH)
    )

    if cache_exists and not force_refresh:
        log("📦 Загружаю векторные представления из кэша...")
        with open(embeddings_list_path, "r", encoding="utf-8") as f:
            embeddings_data = json.load(f)

        all_embs_list = []
        for person_embs in embeddings_data:
            normalized = [
                _l2_normalize(np.array(emb, dtype=np.float32)) for emb in person_embs
            ]
            all_embs_list.append(normalized)

        # Confidences
        if os.path.exists(confidences_list_path):
            with open(confidences_list_path, "r", encoding="utf-8") as f:
                all_confidences_list = json.load(f)
        else:
            all_confidences_list = [
                [1.0] * len(person_embs) for person_embs in all_embs_list
            ]

        with open(config.NAMES_PATH, "r", encoding="utf-8") as f:
            names = json.load(f)
        with open(config.IDS_PATH, "r", encoding="utf-8") as f:
            ids = json.load(f)

        log(f"✅ Кэш загружен ({len(all_embs_list)} лиц).")
        if ids:
            log("👥 Лица из кэша:")
            for pid, name, embs_list, confs_list in zip(
                ids, names, all_embs_list, all_confidences_list
            ):
                avg_conf = sum(confs_list) / len(confs_list) if confs_list else 0.0
                log(
                    f"   - {pid:<4} | {name} "
                    f"({len(embs_list)} векторов, avg confidence={avg_conf:.2f})"
                )

        return all_embs_list, names, ids, all_confidences_list

    # Если кэша нет или нужен refresh → грузим из БД
    all_embs_list, names, ids, all_confidences_list = fetch_embeddings_from_db()

    embeddings_data = [[emb.tolist() for emb in person_embs] for person_embs in all_embs_list]
    with open(embeddings_list_path, "w", encoding="utf-8") as f:
        json.dump(embeddings_data, f, indent=2)

    with open(confidences_list_path, "w", encoding="utf-8") as f:
        json.dump(all_confidences_list, f, indent=2)

    # Старый формат — средние векторные представления по человеку
    if all_embs_list:
        mean_embs = np.array(
            [np.vstack(person_embs).mean(axis=0) for person_embs in all_embs_list]
        )
        if mean_embs.size > 0:
            mean_embs = _l2_normalize(mean_embs)
            np.save(config.EMBEDDINGS_PATH, mean_embs)

    with open(config.NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    with open(config.IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)

    log("💾 Кэш обновлён.")
    return all_embs_list, names, ids, all_confidences_list
