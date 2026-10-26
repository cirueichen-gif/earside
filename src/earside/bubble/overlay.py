"""字幕浮層的 tkinter 進程。獨立 main loop，不跟 asyncio 打架。

可調參數見 config.toml [subtitle] 與 [tuning]（overlay_chars_per_line）。
由核心用 multiprocessing.Queue 餵字，訊息格式：
  ("show", "文字") / ("hide",) / ("quit",)

字級用「負數＝像素」：30 pt 在 150% 縮放下會變成 60px/字，長句直接爆版。
"""

from __future__ import annotations

import ctypes
from queue import Empty

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def run_overlay(queue, options: dict | None = None) -> None:
    import tkinter as tk
    import tkinter.font as tkfont

    options = options or {}
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001 - 舊系統沒有 shcore
        pass

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.0)
    root.configure(bg="#000000")

    family = str(options.get("font", "Microsoft JhengHei"))
    size_px = abs(int(options.get("size", 30)))
    font_spec = (family, -size_px, "bold")
    font_obj = tkfont.Font(family=family, size=-size_px, weight="bold")
    line_height = font_obj.metrics("linespace")
    max_lines = max(1, int(options.get("max_lines", 2)))

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    width = int(screen_w * 0.72)
    height = line_height * max_lines + 24
    position = str(options.get("position", "bottom-center"))
    if position == "bottom-left":
        x = 0
    elif position == "bottom-right":
        x = screen_w - width
    else:
        x = (screen_w - width) // 2
    y = int(screen_h * 0.88) - height
    root.geometry(f"{width}x{height}+{x}+{y}")

    canvas = tk.Canvas(root, bg="#000000", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    alpha = float(options.get("alpha", 0.82))
    usable = max(80, width - 60)
    char_width = max(1, font_obj.measure("字"))
    per_line = max(8, usable // char_width)

    def format_text(text: str) -> str:
        lines: list[str] = []
        for raw in str(text).splitlines() or [""]:
            while len(raw) > per_line:
                lines.append(raw[:per_line])
                raw = raw[per_line:]
            lines.append(raw)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = (lines[-1][:-1] if len(lines[-1]) > 1 else "") + "…"
        return "\n".join(lines)

    def make_click_through() -> None:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            style
            | WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_NOACTIVATE
            | WS_EX_TOOLWINDOW,
        )

    root.after(60, make_click_through)

    def draw(text: str) -> None:
        canvas.delete("all")
        cx, cy = width // 2, height // 2
        for dx, dy, color in ((2, 2, "#000000"), (0, 0, "#ffffff")):
            canvas.create_text(
                cx + dx,
                cy + dy,
                text=format_text(text),
                font=font_spec,
                fill=color,
                width=usable,
                justify="center",
            )

    # 淡出用 generation 編號：新的 show 會讓舊的 after 鏈自己失效，
    # 不然句尾的淡出會把下一句的 alpha 一路壓到 0。
    fade = {"gen": 0, "after_id": None}

    def cancel_fade() -> None:
        fade["gen"] += 1
        if fade["after_id"] is not None:
            try:
                root.after_cancel(fade["after_id"])
            except Exception:  # noqa: BLE001
                pass
            fade["after_id"] = None

    def fade_out(step: int = 1, gen: int = 0) -> None:
        if gen != fade["gen"]:
            return
        root.attributes("-alpha", alpha * max(0.0, 1 - step / 5))
        if step < 5:
            fade["after_id"] = root.after(60, lambda: fade_out(step + 1, gen))

    def poll() -> None:
        try:
            while True:
                msg = queue.get_nowait()
                kind = msg[0]
                if kind == "show":
                    cancel_fade()
                    draw(str(msg[1]))
                    root.attributes("-alpha", alpha)
                    root.attributes("-topmost", True)
                elif kind == "hide":
                    cancel_fade()
                    fade_out(1, fade["gen"])
                elif kind == "quit":
                    root.destroy()
                    return
        except Empty:
            pass
        root.after(50, poll)

    root.after(50, poll)
    root.mainloop()
