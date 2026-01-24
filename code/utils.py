# utils.py
"""
Утилиты: логирование, директории, нормализация, предобработка лиц.
"""

import os
import shutil
from datetime import datetime

import cv2
import numpy as np

import config


def log(msg: str):
    """Стандартный логгер с timestamp."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fix_insightface_model_structure():
    """Исправляет неправильную структуру папок модели InsightFace.
    Проблема: архив antelopev2.zip содержит вложенную папку antelopev2,
    что приводит к структуре models/antelopev2/antelopev2 вместо models/antelopev2.
    Эта функция проверяет и исправляет такую структуру.
    """
    model_name = config.INSIGHTFACE_MODEL
    model_path = os.path.join(config.MODEL_DIR, model_name)
    nested_path = os.path.join(model_path, model_name)
    
    # Проверяем наличие неправильной структуры
    if not os.path.exists(nested_path) or not os.path.isdir(nested_path):
        return  # Структура правильная, ничего не делаем
    
    log(f"🔧 Обнаружена неправильная структура: {nested_path}")
    log(f"   Перемещаю файлы в {model_path}")
    
    try:
        # Сначала проверяем, есть ли файлы модели в правильном месте
        # Если в правильном месте уже есть файлы, удаляем вложенную папку
        correct_files = [f for f in os.listdir(model_path) if f != model_name]
        nested_files = os.listdir(nested_path)
        
        if correct_files:
            # В правильном месте уже есть файлы, просто удаляем вложенную папку
            log(f"   В правильном месте уже есть файлы, удаляю вложенную папку")
            shutil.rmtree(nested_path)
            log(f"✅ Вложенная папка удалена")
            return
        
        # Перемещаем все файлы из вложенной папки в родительскую
        moved_count = 0
        for item in nested_files:
            src = os.path.join(nested_path, item)
            dst = os.path.join(model_path, item)
            
            # Если файл/папка уже существует, удаляем старый и перемещаем новый
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            
            shutil.move(src, dst)
            moved_count += 1
        
        # Удаляем пустую вложенную папку
        try:
            os.rmdir(nested_path)
            log(f"   ✓ Удалена пустая вложенная папка")
        except OSError:
            # Если папка не пуста, удаляем рекурсивно
            shutil.rmtree(nested_path)
            log(f"   ✓ Удалена вложенная папка (рекурсивно)")
        
        log(f"✅ Структура модели исправлена (перемещено {moved_count} элементов)")
    except Exception as e:
        log(f"⚠️ Ошибка при исправлении структуры: {e}")
        import traceback
        log(f"   Traceback: {traceback.format_exc()}")


def ensure_dirs():
    """Создаёт необходимые директории и настраивает INSIGHTFACE_ROOT."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)

    # InsightFace ожидает root/models/antelopev2
    insight_root = os.path.dirname(config.MODEL_DIR) or "/app"
    if insight_root.endswith("/models"):
        insight_root = os.path.dirname(insight_root)
    os.environ["INSIGHTFACE_ROOT"] = insight_root
    
    # Исправляем неправильную структуру папок модели, если она есть
    fix_insightface_model_structure()


def _l2_normalize(v: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """L2-нормализация вектора/массивов по последней оси."""
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def preprocess_face_crop(crop: np.ndarray) -> np.ndarray:
    """Предобработка изображения лица: CLAHE для улучшения контраста."""
    if crop.size == 0:
        return crop
    try:
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception:
        return crop


def adaptive_threshold(face_size: int, base_threshold: float) -> float:
    """Адаптивный порог сходства в зависимости от размера лица (в пикселях)."""
    if face_size < 100:
        # Немного более строгий для маленьких лиц
        return max(0.5, base_threshold - 0.03)
    elif face_size > 200:
        # Немного более мягкий для крупных лиц
        return min(0.6, base_threshold + 0.02)
    return base_threshold
