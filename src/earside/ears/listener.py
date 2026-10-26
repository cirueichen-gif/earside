"""耳朵的組裝：麥克風／檔案 → VAD → ASR 端口 → 文字。"""

from __future__ import annotations

import itertools
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .frames import file_frames, mic_frames, to_wav_bytes
from .vad import SileroVAD, iter_utterances

OnText = Callable[[str, dict], None]


class Listener:
    """背景執行緒跑 VAD＋ASR；事件迴圈不會被音訊卡住。"""

    def __init__(
        self,
        asr=None,
        on_text: OnText | None = None,
        device: str | int | None = None,
        dump_dir: str | None = None,
        on_speech_start=None,
        tuning: dict | None = None,
    ) -> None:
        self.asr = asr
        self.on_text = on_text
        self.on_speech_start = on_speech_start
        self.tuning = tuning or {}
        self.device = device
        self.dump_dir = Path(dump_dir) if dump_dir else None
        if self.dump_dir is not None:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"frames": 0, "dropped": 0, "utterances": 0, "errors": 0, "chars": 0}
        self.ready = threading.Event()
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _counted(self, frames):
        for frame in frames:
            self.stats["frames"] += 1
            yield frame

    def _run(self) -> None:
        try:
            vad = SileroVAD()
            frames = self._counted(mic_frames(self.device, self._stop, self.stats))
            # 先拉一幀：到這裡麥克風才真的開起來，開不起來會丟例外。
            first = next(frames)
            frames = itertools.chain([first], frames)
            self.started_at = time.monotonic()
            self.ready.set()

            for utt in iter_utterances(
                frames, vad, on_start=self.on_speech_start, tuning=self.tuning
            ):
                if self._stop.is_set():
                    break
                self.stats["utterances"] += 1
                utt["rms"] = float(np.sqrt(np.mean(utt["audio"] ** 2)))
                utt["wall_start"] = getattr(self, "started_at", time.monotonic()) + float(
                    utt["start"]
                )
                if self.dump_dir is not None:
                    path = self.dump_dir / f"utt_{int(time.time() * 1000)}.wav"
                    path.write_bytes(to_wav_bytes(utt["audio"]))
                    utt["path"] = str(path)
                text = ""
                if self.asr is not None:
                    try:
                        text = self.asr.transcribe(to_wav_bytes(utt["audio"]), "zh")
                    except Exception:  # noqa: BLE001 - 斷線不該讓耳朵停
                        self.stats["errors"] += 1
                if not text:
                    continue
                self.stats["chars"] += len(text)
                if self.on_text is not None:
                    try:
                        self.on_text(text, utt)
                    except Exception:  # noqa: BLE001 - callback 壞了也不能拖死耳朵
                        pass
        except Exception as exc:  # noqa: BLE001 - 讓 CLI 看得到「起不來」的原因
            self.error = f"{type(exc).__name__}: {exc}"
            self.ready.set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)


def transcribe_file(
    path: str, asr=None, max_seconds: float | None = None, tuning: dict | None = None
) -> list[dict]:
    """離線跑同一條 VAD 管線，給測試與除錯用。"""
    vad = SileroVAD()
    rows: list[dict] = []
    for utt in iter_utterances(file_frames(path, max_seconds), vad, tuning=tuning):
        text = ""
        if asr is not None:
            try:
                text = asr.transcribe(to_wav_bytes(utt["audio"]), "zh")
            except Exception as exc:  # noqa: BLE001
                text = f"<ASR error: {exc}>"
        rows.append(
            {
                "text": text,
                "start": utt["start"],
                "end": utt["end"],
                "seconds": utt["seconds"],
                "cut": utt["cut"],
                "rms": float(np.sqrt(np.mean(utt["audio"] ** 2))),
            }
        )
    return rows
