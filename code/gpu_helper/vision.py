"""YOLO + InsightFace inference for hs-gpu-helper."""

from __future__ import annotations

import numpy as np

import config
from utils import _l2_normalize, adaptive_threshold, preprocess_face_crop


def _face_similarity(
    face_emb: np.ndarray,
    person_embeddings_list: list,
    person_confidences: list | None = None,
) -> float:
    if not person_embeddings_list:
        return 0.0
    face_emb = _l2_normalize(face_emb)
    max_sim = -1.0
    for idx, emb in enumerate(person_embeddings_list):
        emb = _l2_normalize(emb)
        sim = float(np.dot(face_emb, emb))
        if person_confidences and idx < len(person_confidences):
            conf = max(0.5, float(person_confidences[idx]))
            sim *= 0.7 + 0.3 * conf
        if sim > max_sim:
            max_sim = sim
    return max_sim


def detect_objects_and_faces(
    img: np.ndarray,
    yolo,
    face_app,
    all_embeddings_list: list,
    names: list,
    all_confidences_list: list,
) -> list[dict]:
    """
    Returns list of detections:
      {label, confidence, x, y, w, h}
    label may be person(Name) when face matched.
    """
    results = yolo.predict(
        img,
        imgsz=config.YOLO_IMGSZ,
        half=config.YOLO_FP16,
        verbose=False,
    )
    detected: list[dict] = []

    for r in results:
        boxes = r.boxes.xyxy.cpu().numpy()
        classes = r.boxes.cls.cpu().numpy().astype(int)
        confidences = r.boxes.conf.cpu().numpy()

        for (x1, y1, x2, y2), cls, conf in zip(boxes, classes, confidences):
            label = yolo.names.get(cls, str(cls))
            if label in config.YOLO_IGNORE_CLASSES:
                continue
            threshold = (
                config.YOLO_PERSON_CONFIDENCE
                if label == "person"
                else config.YOLO_CONFIDENCE_THRESHOLD
            )
            if conf < threshold:
                continue

            x1i, y1i, x2i, y2i = int(x1), int(y1), int(x2), int(y2)
            w = max(0, x2i - x1i)
            h = max(0, y2i - y1i)
            out_label = label

            if label == "person" and all_embeddings_list:
                ih, iw = img.shape[:2]
                x1c = max(0, x1i)
                y1c = max(0, y1i)
                x2c = min(iw, x2i)
                y2c = min(ih, y2i)
                if x2c > x1c and y2c > y1c:
                    box_w = x2c - x1c
                    box_h = y2c - y1c
                    pad = config.FACE_PADDING_RATIO
                    x1p = max(0, int(x1c - box_w * pad))
                    y1p = max(0, int(y1c - box_h * pad))
                    x2p = min(iw, int(x2c + box_w * pad))
                    y2p = min(ih, int(y2c + box_h * pad))
                    crop = img[y1p:y2p, x1p:x2p]
                    if (
                        crop.size
                        and crop.shape[0] >= config.MIN_FACE_SIZE
                        and crop.shape[1] >= config.MIN_FACE_SIZE
                    ):
                        crop = preprocess_face_crop(crop)
                        try:
                            faces = face_app.get(crop, max_num=config.MAX_FACES_PER_CROP)
                        except Exception:
                            faces = []
                        best_name = None
                        best_sim = 0.0
                        for face in faces or []:
                            try:
                                face_emb = np.asarray(face.embedding, dtype=np.float32)
                                if face_emb.ndim != 1:
                                    continue
                                sims = []
                                for idx, person_embs in enumerate(all_embeddings_list):
                                    confs = (
                                        all_confidences_list[idx]
                                        if idx < len(all_confidences_list)
                                        else None
                                    )
                                    sim = _face_similarity(face_emb, person_embs, confs)
                                    pname = names[idx] if idx < len(names) else None
                                    sims.append((sim, pname))
                                if not sims:
                                    continue
                                sims.sort(reverse=True, key=lambda x: x[0])
                                sim0, name0 = sims[0]
                                second = sims[1][0] if len(sims) > 1 else 0.0
                                diff = sim0 - second
                                thr = adaptive_threshold(
                                    max(box_w, box_h), config.FACE_SIM_THRESHOLD
                                )
                                high = sim0 >= thr + 0.1
                                good_diff = diff >= config.MIN_SIM_DIFF
                                if sim0 >= thr and (good_diff or high) and name0:
                                    if sim0 > best_sim:
                                        best_sim = sim0
                                        best_name = name0
                            except Exception:
                                continue
                        if best_name:
                            out_label = f"person({best_name})"

            detected.append(
                {
                    "label": out_label,
                    "confidence": float(conf),
                    "x": x1i,
                    "y": y1i,
                    "w": w,
                    "h": h,
                }
            )

    return detected
