"""Screen and window capture module for earside.

Provides window discovery, coordinate mapping, and frame capture using mss
or native APIs. Supports cropping normalized regions relative to the window
client area.

Note:
    When using the default 'mss' backend, windows that are obscured or occluded
    by other windows cannot have their contents captured properly (mss captures
    desktop screen pixels).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import re
from typing import Tuple

import numpy as np

try:
    import mss
except ImportError:
    mss = None

try:
    import windows_capture
except ImportError:
    windows_capture = None

logger = logging.getLogger(__name__)

# Ensure Per-Monitor DPI Aware (V2 or V1) on Windows
_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi
_shcore = getattr(ctypes.windll, "shcore", None)

try:
    if _shcore and hasattr(_shcore, "SetProcessDpiAwareness"):
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        _shcore.SetProcessDpiAwareness(2)
    elif hasattr(_user32, "SetProcessDpiAwarenessContext"):
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    else:
        _user32.SetProcessDPIAware()
except Exception as e:
    logger.debug("Failed to set DPI awareness: %s", e)


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_window(window_title_regex: str | None = None) -> int:
    """Find a window handle matching the given regex, or return foreground window.

    Args:
        window_title_regex: Regular expression to match against window title
            (case-insensitive). If None, returns the current foreground window.

    Returns:
        HWND handle of the window.

    Raises:
        RuntimeError: If no matching visible window or foreground window is found.
    """
    if window_title_regex is None:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd or not _user32.IsWindow(hwnd):
            raise RuntimeError("No foreground window found.")
        return int(hwnd)

    pattern = re.compile(window_title_regex, re.IGNORECASE)
    matched_hwnds: list[int] = []

    def _enum_proc(hwnd: int, _: int) -> bool:
        if _user32.IsWindowVisible(hwnd):
            length = _user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                _user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if pattern.search(title):
                    matched_hwnds.append(int(hwnd))
        return True

    _user32.EnumWindows(WNDENUMPROC(_enum_proc), 0)

    if not matched_hwnds:
        raise RuntimeError(f"No visible window matching pattern '{window_title_regex}' found.")

    return matched_hwnds[0]


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Get the physical window bounds (left, top, width, height).

    Attempts DwmGetWindowAttribute with DWMWA_EXTENDED_FRAME_BOUNDS (9).
    Falls back to GetWindowRect if DWM call fails.
    """
    rect = _RECT()
    # DWMWA_EXTENDED_FRAME_BOUNDS = 9
    hr = _dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    if hr == 0:
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    # Fallback to GetWindowRect
    if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top

    raise RuntimeError(f"Failed to get window rect for hwnd {hwnd}.")


def get_client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Get the screen coordinates and size of the window client area.

    Returns:
        (left, top, width, height) in screen physical pixels.
    """
    rect = _RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        # Fallback to window rect
        return get_window_rect(hwnd)

    pt = _POINT(0, 0)
    if not _user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return get_window_rect(hwnd)

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return pt.x, pt.y, width, height


def crop_norm(frame: np.ndarray, rect_norm: tuple[float, float, float, float]) -> np.ndarray:
    """把已抓到的整窗畫面裁出歸一化 ROI（給多區共用一次 grab 用）。"""
    nx, ny, nw, nh = rect_norm
    nx = max(0.0, min(1.0, float(nx)))
    ny = max(0.0, min(1.0, float(ny)))
    nw = max(0.0, min(1.0 - nx, float(nw)))
    nh = max(0.0, min(1.0 - ny, float(nh)))

    h, w = frame.shape[:2]
    px = int(round(nx * w))
    py = int(round(ny * h))
    pw = int(round(nw * w))
    ph = int(round(nh * h))
    px = max(0, min(w, px))
    py = max(0, min(h, py))
    pw = max(1, min(w - px, pw))
    ph = max(1, min(h - py, ph))
    return np.ascontiguousarray(frame[py : py + ph, px : px + pw])


class CaptureSession:
    """Session for capturing frames from a target window.

    Supports capturing the whole window / client area and cropping normalized ROIs.
    """

    def __init__(
        self,
        window_title_regex: str | None = None,
        backend: str = "auto",
        hwnd: int | None = None,
    ) -> None:
        """Initialize capture session.

        Args:
            window_title_regex: Regex for window title (case-insensitive).
                If None, uses foreground window.
            backend: Capture backend ("auto", "mss", "wgc").
            hwnd: Optional explicit window handle.
        """
        if hwnd is not None:
            self.hwnd = hwnd
        else:
            self.hwnd = find_window(window_title_regex)

        self._closed = False

        if backend == "auto":
            # WGC 尚未實作；auto 一律走 mss，避免「裝了 windows_capture 反而壞掉」。
            self._backend = "mss"
        elif backend in ("mss", "wgc"):
            self._backend = backend
        else:
            raise ValueError(f"Unknown backend: {backend}")

        if self._backend == "mss":
            if mss is None:
                raise ImportError("mss is required for mss capture backend. Run pip install mss.")
            self._sct = mss.MSS()
        else:
            self._sct = None

    @property
    def backend_name(self) -> str:
        """Name of the active capture backend ('mss' or 'wgc')."""
        return self._backend

    def window_rect(self) -> tuple[int, int, int, int]:
        """Return (left, top, width, height) of the window in physical pixels."""
        return get_window_rect(self.hwnd)

    def client_rect(self) -> tuple[int, int, int, int]:
        """Return (left, top, width, height) of the client area in physical pixels."""
        return get_client_rect(self.hwnd)

    def grab(self) -> np.ndarray:
        """Grab the full client area of the window as a BGR image.

        Returns:
            np.ndarray of shape (H, W, 3), dtype uint8, in BGR format.

        Note:
            If mss backend is used, any overlaying windows will obscure the capture.
        """
        if self._closed:
            raise RuntimeError("CaptureSession is closed.")

        # Plan §6.1 specifies coordinates relative to client area
        left, top, width, height = self.client_rect()
        if width <= 0 or height <= 0:
            # Fall back to window rect if client rect is zero (e.g. minimized)
            left, top, width, height = self.window_rect()

        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid window dimensions: {width}x{height}")

        if self._backend == "mss":
            bbox = {"left": left, "top": top, "width": width, "height": height}
            raw = self._sct.grab(bbox)
            # mss returns BGRA buffer
            img = np.array(raw, dtype=np.uint8)
            bgr = np.ascontiguousarray(img[:, :, :3])
            return bgr
        else:
            raise NotImplementedError("WGC backend is not yet implemented.")

    def grab_region(self, rect_norm: tuple[float, float, float, float]) -> np.ndarray:
        """Grab a normalized sub-region [x, y, w, h] (0.0 - 1.0) relative to client area.

        Coordinates are clamped to [0.0, 1.0] to prevent out-of-bounds exceptions.
        """
        return crop_norm(self.grab(), rect_norm)

    def close(self) -> None:
        """Release capture resources."""
        if not self._closed:
            self._closed = True
            if self._sct is not None:
                try:
                    self._sct.close()
                except Exception:
                    pass
                self._sct = None

    def __enter__(self) -> CaptureSession:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
