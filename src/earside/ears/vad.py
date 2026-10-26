"""Silero VAD 與切句。參數照 07 驗過的那組，不改。

可調參數見 config.toml [tuning]（vad_*）；這裡的常數只是預設值。
"""

from __future__ import annotations

import collections
import statistics
from typing import Iterator

import numpy as np

from .frames import FRAME, FRAME_S, SR

VAD_THRESH = 0.5
PRE_ROLL_S = 0.30
ONSET_S = 0.25  # 連續 250ms 人聲才 confirmed（單幀誤觸發太多）
HANGOVER_S = 1.00  # 0.7 會把「我問說」「我起」切兩半
MIN_SPEECH_S = 0.25
MAX_UTTER_S = 15.0

PRE_FRAMES = int(round(PRE_ROLL_S / FRAME_S))
ONSET_FRAMES = max(1, int(round(ONSET_S / FRAME_S)))
HANGOVER_FRAMES = int(round(HANGOVER_S / FRAME_S))
MAX_FRAMES = int(round(MAX_UTTER_S / FRAME_S))


class _OnnxVAD:
    """沒有 torch 的環境（冷凍 exe）用 onnxruntime 跑同一個 Silero 模型。"""

    def __init__(self) -> None:
        import onnxruntime as ort

        from ..core.paths import project_root

        model = project_root() / "models" / "silero_vad.onnx"
        if not model.is_file():
            raise RuntimeError(f"找不到 VAD 模型：{model}")
        self.sess = ort.InferenceSession(
            str(model), providers=["CPUExecutionProvider"]
        )
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)

    def prob(self, frame: np.ndarray) -> float:
        x = np.asarray(frame, dtype=np.float32).reshape(1, -1)
        out, state = self.sess.run(
            None,
            {
                "input": x,
                "state": self.state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        self.state = np.asarray(state, dtype=np.float32)
        return float(out[0][0])


class SileroVAD:
    def __init__(self) -> None:
        self._onnx = None
        try:
            from silero_vad import load_silero_vad

            try:
                self.model = load_silero_vad(onnx=True)
            except Exception:  # noqa: BLE001 - 沒 ONNX 就退回 JIT
                self.model = load_silero_vad()
        except Exception:  # noqa: BLE001 - 冷凍 exe 沒有 torch：走 ONNX
            self.model = None
            self._onnx = _OnnxVAD()

    def prob(self, frame: np.ndarray) -> float:
        if self._onnx is not None:
            return self._onnx.prob(frame)
        import torch

        return float(self.model(torch.from_numpy(frame), SR))

    def reset(self) -> None:
        if self._onnx is not None:
            self._onnx.reset()
        else:
            self.model.reset_states()


def iter_utterances(
    frames: Iterator[np.ndarray],
    vad: SileroVAD,
    on_start=None,
    tuning: dict | None = None,
) -> Iterator[dict]:
    """音框流 → 一句一句的音訊（含 pre-roll、去掉 hangover 尾巴）。

    on_start：偵測到「開始講話」就立刻回呼（不等句尾），barge-in 用。
    tuning：從 config 的 [tuning] 來的覆蓋值；不給就用模組預設。
    """
    t = tuning or {}
    threshold = float(t.get("vad_threshold", VAD_THRESH))
    pre_frames = max(1, int(round(float(t.get("vad_pre_roll_s", PRE_ROLL_S)) / FRAME_S)))
    onset_frames = max(1, int(t.get("vad_onset_frames", ONSET_FRAMES)))
    hangover_frames = max(
        1, int(round(float(t.get("vad_hangover_s", HANGOVER_S)) / FRAME_S))
    )
    min_speech_s = float(t.get("vad_min_speech_s", MIN_SPEECH_S))
    max_frames = max(
        1, int(round(float(t.get("vad_max_utter_s", MAX_UTTER_S)) / FRAME_S))
    )

    vad.reset()
    preroll: collections.deque[np.ndarray] = collections.deque(maxlen=pre_frames)
    buf: list[np.ndarray] = []
    active = False
    above = 0
    sil_frames = 0
    n = 0
    start = 0.0

    for frame in frames:
        p = vad.prob(frame)
        n += 1

        if not active:
            preroll.append(frame)
            if p >= threshold:
                above += 1
                if above < onset_frames:
                    continue
                active = True
                buf = list(preroll)
                preroll.clear()
                sil_frames = 0
                above = 0
                start = (n - len(buf)) * FRAME_S
                if on_start is not None:
                    try:
                        on_start()
                    except Exception:  # noqa: BLE001 - 回呼壞了不能拖死耳朵
                        pass
            else:
                above = 0
            continue

        buf.append(frame)
        sil_frames = 0 if p >= threshold else sil_frames + 1

        too_long = len(buf) >= max_frames
        finished = sil_frames >= hangover_frames
        if not (too_long or finished):
            continue

        if finished and sil_frames:
            audio = np.concatenate(buf[:-sil_frames])
            end = n * FRAME_S - sil_frames * FRAME_S
        else:
            audio = np.concatenate(buf)
            end = n * FRAME_S

        spoken = len(audio) / SR
        active = False
        buf = []
        sil_frames = 0

        if spoken >= min_speech_s:
            yield {
                "audio": audio,
                "start": start,
                "end": end,
                "seconds": spoken,
                "cut": "max" if too_long else "silence",
            }

    if active and buf:
        audio = np.concatenate(buf)
        spoken = len(audio) / SR
        if spoken >= min_speech_s:
            yield {
                "audio": audio,
                "start": start,
                "end": n * FRAME_S,
                "seconds": spoken,
                "cut": "eof",
            }


def speech_ratio(probs: list[float], threshold: float = VAD_THRESH) -> float:
    return statistics.fmean(p >= threshold for p in probs) if probs else 0.0
