#!/usr/bin/env python3
"""hs-gpu-helper HTTP API (GPU inference only). Immich DB не используется."""

from __future__ import annotations

import os
import threading

# Quiet Russian app logs from models/embeddings/utils
os.environ.setdefault("YOLO_VERBOSE", "False")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import utils

utils.log = lambda msg: None  # noqa: E731

import cv2
import numpy as np
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from embeddings import (
    faces_from_pickle_blob,
    load_or_refresh_cache,
    save_faces_cache,
)
from gpu_helper.audio_infer import YamnetEngine
from gpu_helper.logutil import audio_stats, vision_stats
from gpu_helper.vision import detect_objects_and_faces
from models import init_face_analysis, init_yolo

_state_lock = threading.Lock()
_ready = False
_yolo = None
_face_app = None
_embeddings = ([], [], [], [])
_yamnet = YamnetEngine()


def _set_embeddings(embs, names, ids, confs) -> int:
    global _embeddings
    with _state_lock:
        _embeddings = (embs, names, ids, confs)
    return len(names)


def _init_models() -> None:
    global _ready, _yolo, _face_app, _embeddings
    print("[init] loading models", flush=True)
    _yolo = init_yolo()
    print("[init] yolo ready", flush=True)
    _face_app = init_face_analysis()
    print("[init] insightface ready", flush=True)
    # Только локальный кэш (заливка с home-sentinel). В Immich DB не ходим.
    try:
        _embeddings = load_or_refresh_cache(force_refresh=False, allow_db=False)
        print(f"[init] faces={len(_embeddings[0])} (local cache)", flush=True)
    except Exception as e:
        _embeddings = ([], [], [], [])
        print(f"[init] faces=0 (no cache): {e}", flush=True)
    try:
        _yamnet.load()
    except Exception as e:
        print(f"[init] yamnet failed: {e}", flush=True)
    with _state_lock:
        _ready = True
    print("[init] ready", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_init_models, daemon=True, name="model-init").start()
    yield


app = FastAPI(title="hs-gpu-helper", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health")
def health():
    with _state_lock:
        ready = _ready
        n_faces = len(_embeddings[0])
    return {
        "ok": True,
        "ready": ready,
        "faces": n_faces,
        "vision": vision_stats.snapshot(),
        "audio": audio_stats.snapshot(),
    }


@app.post("/v1/faces")
async def upload_faces(request: Request):
    """Принимает pickle-пакет лиц от home-sentinel (без Immich на helper)."""
    with _state_lock:
        ready = _ready
    if not ready:
        return JSONResponse({"error": "not_ready"}, status_code=503)

    body = await request.body()
    if not body:
        return JSONResponse({"error": "empty_body"}, status_code=400)

    try:
        embs, names, ids, confs = faces_from_pickle_blob(body)
        n = _set_embeddings(embs, names, ids, confs)
        try:
            save_faces_cache(embs, names, ids, confs)
        except Exception as e:
            print(f"[faces] cache save failed: {e}", flush=True)
        print(f"[faces] uploaded people={n}", flush=True)
        return {"ok": True, "people": n}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/v1/vision")
async def vision(request: Request):
    vision_stats.mark_received()
    with _state_lock:
        ready = _ready
        yolo = _yolo
        face_app = _face_app
        embs, names, _ids, confs = _embeddings
    if not ready or yolo is None or face_app is None:
        vision_stats.mark_error()
        return JSONResponse({"error": "not_ready"}, status_code=503)

    body = await request.body()
    if not body:
        vision_stats.mark_error()
        return JSONResponse({"error": "empty_body"}, status_code=400)

    arr = np.frombuffer(body, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        vision_stats.mark_error()
        return JSONResponse({"error": "bad_image"}, status_code=400)

    try:
        objects = detect_objects_and_faces(img, yolo, face_app, embs, names, confs)
        vision_stats.mark_processed()
        return {"objects": objects}
    except Exception as e:
        vision_stats.mark_error()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/v1/audio")
async def audio(request: Request):
    audio_stats.mark_received()
    with _state_lock:
        ready = _ready
    if not ready:
        audio_stats.mark_error()
        return JSONResponse({"error": "not_ready"}, status_code=503)

    body = await request.body()
    if not body:
        audio_stats.mark_error()
        return JSONResponse({"error": "empty_body"}, status_code=400)

    try:
        sounds = _yamnet.classify_pcm_s16le(body)
        audio_stats.mark_processed()
        return {"sounds": sounds}
    except Exception as e:
        audio_stats.mark_error()
        return JSONResponse({"error": str(e)}, status_code=500)


def main():
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
