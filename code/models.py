# models.py
"""
Инициализация моделей: YOLOv11 и InsightFace (antelopev2).
"""

import os

from insightface.app import FaceAnalysis
from ultralytics import YOLO

import config
from utils import log


def init_face_analysis():
    """Инициализация InsightFace (antelopev2) с CUDA/CPU fallback."""
    det_size = (config.FACE_DET_SIZE, config.FACE_DET_SIZE)
    insight_root = os.environ.get("INSIGHTFACE_ROOT", "/app")

    log(
        f"🧠 Инициализация InsightFace ({config.INSIGHTFACE_MODEL}), "
        f"root={insight_root}, det_size={det_size}"
    )

    try:
        app = FaceAnalysis(
            name=config.INSIGHTFACE_MODEL,
            root=insight_root,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=det_size)
        log(f"✅ InsightFace запущен с CUDA/CPU, det_size={det_size}.")
        return app
    except Exception as e:
        log(f"⚠️ Ошибка GPU InsightFace: {e}, пробую CPU...")
        app = FaceAnalysis(
            name=config.INSIGHTFACE_MODEL,
            root=insight_root,
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=det_size)
        log(f"✅ InsightFace запущен на CPU, det_size={det_size}.")
        return app


def init_yolo():
    """Инициализация YOLOv11 модели (GPU → CPU fallback)."""
    log(f"🤖 Инициализация YOLOv11 модели: {config.YOLO_MODEL}")

    path = config.YOLO_MODEL
    if not os.path.isabs(path):
        os.makedirs(config.MODEL_DIR, exist_ok=True)
        path = os.path.join(config.MODEL_DIR, config.YOLO_MODEL)

    model = YOLO(path)

    if config.YOLO_FORCE_GPU:
        try:
            model.to("cuda")
            log("✅ YOLO GPU.")
        except Exception as e:
            log(f"⚠️ YOLO GPU не удалось ({e}), CPU...")
            model.to("cpu")
    else:
        model.to("cpu")
        log("YOLO CPU.")

    return model
