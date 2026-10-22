"""YAMNet inference for hs-gpu-helper."""

from __future__ import annotations

import csv
from typing import Any

import numpy as np

import config


class YamnetEngine:
    def __init__(self):
        self.model = None
        self.class_names: dict[int, str] = {}
        self.tracked_indices: list[tuple[int, str]] = []
        self.window_size = 15680

    def load(self) -> None:
        if not config.YAMNET_CLASSES:
            print("[init] yamnet skipped (YAMNET_CLASSES empty)", flush=True)
            return
        import tensorflow as tf  # noqa: F401
        import tensorflow_hub as hub

        self.model = hub.load("https://tfhub.dev/google/yamnet/1")
        class_map_path = self.model.class_map_path().numpy().decode("utf-8")
        with open(class_map_path, "r") as f:
            reader = csv.reader(f)
            for line_num, row in enumerate(reader):
                if line_num == 0 or len(row) < 3:
                    continue
                try:
                    self.class_names[int(row[0])] = row[2]
                except ValueError:
                    continue
        for idx, name in self.class_names.items():
            if name.lower() in config.YAMNET_CLASSES:
                self.tracked_indices.append((idx, name))
        print(
            f"[init] yamnet ready tracked={len(self.tracked_indices)}",
            flush=True,
        )

    def classify_pcm_s16le(self, pcm_bytes: bytes) -> list[dict[str, Any]]:
        if not self.model or not self.tracked_indices:
            return []
        pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
        if pcm.size < self.window_size:
            return []
        audio_float = pcm.astype(np.float32) / 32768.0
        if audio_float.size > self.window_size:
            audio_float = audio_float[-self.window_size :]
        elif audio_float.size < self.window_size:
            audio_float = np.concatenate(
                [
                    audio_float,
                    np.zeros(self.window_size - audio_float.size, dtype=np.float32),
                ]
            )

        scores, _, _ = self.model(audio_float)
        scores_np = scores.numpy()
        scores_mean = np.mean(scores_np, axis=0) if scores_np.ndim == 2 else scores_np

        default_threshold = config.YAMNET_CONFIDENCE_THRESHOLD
        hits: list[dict[str, Any]] = []
        for idx, class_name in self.tracked_indices:
            if idx >= len(scores_mean):
                continue
            confidence = float(scores_mean[idx])
            threshold = config.YAMNET_CLASS_THRESHOLDS.get(
                class_name.lower(), default_threshold
            )
            if confidence >= threshold:
                hits.append({"name": class_name, "confidence": confidence})
        hits.sort(key=lambda x: x["confidence"], reverse=True)
        return hits
