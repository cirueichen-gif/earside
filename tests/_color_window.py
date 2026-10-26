"""測試用：一個會換顏色的置頂視窗，讓 capture + change 規則有東西可抓。"""

from __future__ import annotations

import tkinter as tk

COLORS = ["#ff0000", "#00ff00", "#0000ff", "#ffffff"]


def main() -> None:
    root = tk.Tk()
    root.title("earside-capture-test")
    root.geometry("400x300+120+120")
    root.attributes("-topmost", True)

    def tick(index: int = 0) -> None:
        root.configure(bg=COLORS[index % len(COLORS)])
        root.after(400, tick, index + 1)

    tick()
    root.mainloop()


if __name__ == "__main__":
    main()
