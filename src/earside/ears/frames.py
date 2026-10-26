"""音框來源：麥克風與檔案，吐一樣的 512@16k float32。

重取樣用 soxr 串流（抗混疊、跨音框保留濾波器狀態）。
線性內插會把 8k 以上全部折回語音頻段——VAD 不在乎，ASR 會。
"""

from __future__ import annotations

import queue
import threading
from typing import Iterator

import numpy as np

try:
    import soxr
except Exception:  # noqa: BLE001 - 沒裝 soxr 才退回線性（會混疊，但不擋啟動）
    soxr = None

SR = 16000
FRAME = 512  # 32 ms @ 16k，Silero 規定的窗長
FRAME_S = FRAME / SR


def _fallback_resample(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or len(x) == 0:
        return x
    n = int(len(x) * dst_sr / src_sr)
    return np.interp(
        np.linspace(0, len(x) - 1, n), np.arange(len(x)), x
    ).astype(np.float32)


def resolve_device(device: str | int | None) -> str | int | None:
    """設定寫「名字片段」也能找到裝置；空字串＝系統預設。"""
    if device is None or device == "":
        return None
    if isinstance(device, int):
        return device
    try:
        import sounddevice as sd

        needle = device.lower()
        for index, info in enumerate(sd.query_devices()):
            if info["max_input_channels"] > 0 and needle in info["name"].lower():
                return index
    except Exception:  # noqa: BLE001 - 找不到就原樣丟給 PortAudio
        pass
    return device


def file_frames(path: str, max_seconds: float | None = None) -> Iterator[np.ndarray]:
    import soundfile as sf

    info = sf.info(path)
    frames = int(max_seconds * info.samplerate) if max_seconds else -1
    data, file_sr = sf.read(path, frames=frames, dtype="float32", always_2d=True)
    x = data[:, 0]
    if file_sr != SR and len(x):
        x = (
            soxr.resample(x, file_sr, SR).astype(np.float32)
            if soxr is not None
            else _fallback_resample(x, file_sr, SR)
        )
    for i in range(0, len(x) - FRAME + 1, FRAME):
        yield np.ascontiguousarray(x[i : i + FRAME], dtype=np.float32)


def mic_frames(
    device: str | int | None = None,
    stop_event: threading.Event | None = None,
    stats: dict | None = None,
) -> Iterator[np.ndarray]:
    """PortAudio callback 只做複製；重取樣在 consumer 這側做（單一執行緒、狀態連續）。"""
    import sounddevice as sd

    device = resolve_device(device)
    info = sd.query_devices(device, "input")
    native_sr = int(info["default_samplerate"] or SR)
    native_block = max(FRAME, int(round(FRAME * native_sr / SR)))

    q: queue.Queue[np.ndarray] = queue.Queue(maxsize=256)

    def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
        chunk = indata[:, 0].copy()
        try:
            q.put_nowait(chunk)
        except queue.Full:
            if stats is not None:
                stats["dropped"] = stats.get("dropped", 0) + 1
            try:
                q.get_nowait()
                q.put_nowait(chunk)
            except (queue.Empty, queue.Full):
                pass

    stream = sd.InputStream(
        samplerate=native_sr,
        channels=1,
        dtype="float32",
        blocksize=native_block,
        device=device,
        callback=callback,
    )
    stream.start()

    resampler = (
        soxr.ResampleStream(native_sr, SR, 1, dtype="float32")
        if soxr is not None and native_sr != SR
        else None
    )
    pending = np.zeros(0, dtype=np.float32)

    try:
        while not (stop_event and stop_event.is_set()):
            try:
                chunk = q.get(timeout=0.2)
            except queue.Empty:
                continue
            if resampler is not None:
                out = np.asarray(
                    resampler.resample_chunk(chunk, last=False), dtype=np.float32
                ).reshape(-1)
            else:
                out = chunk
            if out.size == 0:
                continue
            pending = np.concatenate([pending, out]) if pending.size else out
            while pending.size >= FRAME:
                yield np.ascontiguousarray(pending[:FRAME])
                pending = pending[FRAME:]
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:  # noqa: BLE001
            pass


def to_wav_bytes(audio: np.ndarray, sr: int = SR) -> bytes:
    import io

    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()
