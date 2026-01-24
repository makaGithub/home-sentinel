# models.py
"""
Инициализация моделей: YOLOv11 и InsightFace (antelopev2).
"""

import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from insightface.app import FaceAnalysis
from ultralytics import YOLO

import config
from utils import log


class _SuppressOutput:
    """Контекстный менеджер для подавления stdout/stderr (включая C-level)."""
    def __enter__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._devnull = open(os.devnull, 'w')
        sys.stdout = self._devnull
        sys.stderr = self._devnull
        return self
    
    def __exit__(self, *args):
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        self._devnull.close()


def init_face_analysis():
    """Инициализация InsightFace (antelopev2) с CUDA/CPU fallback."""
    from utils import fix_insightface_model_structure
    
    det_size = (config.FACE_DET_SIZE, config.FACE_DET_SIZE)
    insight_root = os.environ.get("INSIGHTFACE_ROOT", "/app")

    log(f"🧠 Инициализация системы распознавания лиц InsightFace ({config.INSIGHTFACE_MODEL})...")

    # Исправляем структуру ДО создания FaceAnalysis (на случай, если модель уже распакована)
    fix_insightface_model_structure()

    try:
        # Подавляем вывод ONNX Runtime (Applied providers, find model)
        with _SuppressOutput():
            # Создаём FaceAnalysis - здесь InsightFace может распаковать модель
            app = FaceAnalysis(
                name=config.INSIGHTFACE_MODEL,
                root=insight_root,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            # Исправляем структуру сразу ПОСЛЕ создания (если InsightFace только что распаковал)
            fix_insightface_model_structure()
            # Теперь prepare() использует правильную структуру
            app.prepare(ctx_id=0, det_size=det_size)
        log(f"✅ Система распознавания лиц InsightFace готова (GPU)")
        return app
    except Exception as e:
        log(f"⚠️ Ошибка GPU InsightFace: {e}, пробую CPU...")
        # Подавляем вывод ONNX Runtime
        with _SuppressOutput():
            # Исправляем структуру перед повторной попыткой
            fix_insightface_model_structure()
            app = FaceAnalysis(
                name=config.INSIGHTFACE_MODEL,
                root=insight_root,
                providers=["CPUExecutionProvider"],
            )
            # Исправляем структуру сразу ПОСЛЕ создания (если InsightFace только что распаковал)
            fix_insightface_model_structure()
            # Теперь prepare() использует правильную структуру
            app.prepare(ctx_id=0, det_size=det_size)
        log(f"✅ Система распознавания лиц InsightFace готова (CPU)")
        return app


def init_yolo():
    """Инициализация YOLOv11 модели (GPU → CPU fallback)."""
    log(f"🤖 Инициализация системы обнаружения объектов YOLO ({config.YOLO_MODEL})...")

    path = config.YOLO_MODEL
    if not os.path.isabs(path):
        os.makedirs(config.MODEL_DIR, exist_ok=True)
        path = os.path.join(config.MODEL_DIR, config.YOLO_MODEL)

    model = YOLO(path)

    if config.YOLO_FORCE_GPU:
        try:
            model.to("cuda")
            # FP16 включаем на стадии predict() (Ultralytics сначала fuse() в FP32)
            log("✅ Система обнаружения объектов YOLO готова (GPU)")
        except Exception as e:
            log(f"⚠️ YOLO GPU не удалось ({e}), переключаюсь на CPU...")
            model.to("cpu")
            log("✅ Система обнаружения объектов YOLO готова (CPU)")
    else:
        model.to("cpu")
        log("✅ Система обнаружения объектов YOLO готова (CPU)")

    return model
