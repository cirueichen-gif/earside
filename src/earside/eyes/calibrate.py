"""Visual region calibration wizard and preset builder for earside.

Provides:
- normalize_rect(x1, y1, x2, y2, w, h): Pure function mapping pixel drags to normalized [0, 1].
- build_preset(...): Pure function constructing a valid Preset dictionary.
- save_preset(preset_dict, path): Pure function saving preset dict as UTF-8 JSON.
- run_editor(preset_path=None): Tkinter UI for capturing windows, dragging regions, and editing rules.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def normalize_rect(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: float,
    height: float,
) -> Tuple[float, float, float, float]:
    """Normalize pixel coordinates to [0, 1] relative to (width, height).

    Supports dragging in any direction (x1/y1 can be greater than x2/y2).
    Coordinates are clamped to [0.0, 1.0].
    Width and height in normalized space will span at least 1 pixel equivalent
    (or a small positive epsilon if image dimension is <= 0).

    Returns:
        (nx, ny, nw, nh) with all values in [0.0, 1.0].
    """
    w = max(1.0, float(width))
    h = max(1.0, float(height))

    # Min pixel size is 1px
    min_px = 1.0

    left_px = min(float(x1), float(x2))
    right_px = max(float(x1), float(x2))
    top_px = min(float(y1), float(y2))
    bottom_px = max(float(y1), float(y2))

    # Clamp bounds to [0, w] and [0, h]
    left_px = max(0.0, min(w, left_px))
    right_px = max(0.0, min(w, right_px))
    top_px = max(0.0, min(h, top_px))
    bottom_px = max(0.0, min(h, bottom_px))

    rect_w_px = max(min_px, right_px - left_px)
    rect_h_px = max(min_px, bottom_px - top_px)

    # Ensure rect fits inside boundary if left/top are close to right/bottom
    if left_px + rect_w_px > w:
        left_px = max(0.0, w - rect_w_px)
    if top_px + rect_h_px > h:
        top_px = max(0.0, h - rect_h_px)

    nx = left_px / w
    ny = top_px / h
    nw = rect_w_px / w
    nh = rect_h_px / h

    # Clamp round-off
    nx = max(0.0, min(1.0, round(nx, 4)))
    ny = max(0.0, min(1.0, round(ny, 4)))
    nw = max(0.0, min(1.0 - nx, round(nw, 4)))
    nh = max(0.0, min(1.0 - ny, round(nh, 4)))

    return nx, ny, nw, nh


def build_preset(
    preset_id: str,
    name: str,
    window_title_regex: str,
    reference_aspect: float = 1.7778,
    game_type: str = "generic",
    enabled: bool = True,
    sensitivity: float = 1.0,
    regions: Optional[List[Dict[str, Any]]] = None,
    triggers: Optional[List[Dict[str, Any]]] = None,
    vision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construct a dictionary representation conforming to the Preset schema."""
    clean_id = str(preset_id).strip() or "untitled-preset"
    clean_name = str(name).strip() or "Untitled Preset"
    clean_regex = str(window_title_regex).strip()

    sens = max(0.25, min(4.0, float(sensitivity)))
    aspect = max(0.01, float(reference_aspect))

    parsed_regions: List[Dict[str, Any]] = []
    if regions:
        for r in regions:
            r_name = str(r.get("name", "")).strip() or "unnamed_region"
            rect = r.get("rect", [0.0, 0.0, 1.0, 1.0])
            nx, ny, nw, nh = (float(v) for v in rect)
            interval_ms = int(r.get("interval_ms", 300))
            rule = dict(r.get("rule", {"type": "change"}))
            parsed_regions.append({
                "name": r_name,
                "rect": [round(nx, 4), round(ny, 4), round(nw, 4), round(nh, 4)],
                "interval_ms": max(10, interval_ms),
                "rule": rule,
            })

    return {
        "id": clean_id,
        "name": clean_name,
        "game_type": str(game_type).strip() or "generic",
        "enabled": bool(enabled),
        "sensitivity": round(sens, 2),
        "match": {"window_title_regex": clean_regex},
        "reference_aspect": round(aspect, 4),
        "regions": parsed_regions,
        "triggers": list(triggers or []),
        "vision": dict(vision or {}),
    }


def save_preset(preset_dict: Dict[str, Any], path: Union[str, Path]) -> Path:
    """Save preset dictionary as a formatted UTF-8 JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(preset_dict, f, ensure_ascii=False, indent=2)
    return p


def run_editor(preset_path: Optional[Union[str, Path]] = None) -> None:
    """Launch the Tkinter visual calibration editor.

    Does not block indefinitely if called from an external mainloop, but starts
    its own event loop if run as standalone. Opens in a separate Toplevel (or Tk).
    """
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
    import cv2
    from PIL import Image, ImageTk

    from earside.eyes.capture import CaptureSession
    from earside.eyes.preset import load_preset

    # Determine if a root Tk already exists
    created_root = False
    try:
        root = tk._default_root
        if root is None:
            root = tk.Tk()
            created_root = True
            root.title("Earside 區域校準精靈")
            win = root
        else:
            win = tk.Toplevel(root)
            win.title("Earside 區域校準精靈")
    except Exception:
        root = tk.Tk()
        created_root = True
        root.title("Earside 區域校準精靈")
        win = root

    win.geometry("1100x720")

    # State variables
    current_image_bgr: Optional[Any] = None
    current_image_tk: Optional[Any] = None
    display_scale: float = 1.0
    display_offset_x: int = 0
    display_offset_y: int = 0
    drag_start: Optional[Tuple[int, int]] = None
    current_rect_item: Optional[int] = None

    regions_data: List[Dict[str, Any]] = []

    # Top Control Bar
    top_bar = ttk.Frame(win, padding=6)
    top_bar.pack(side=tk.TOP, fill=tk.X)

    ttk.Label(top_bar, text="視窗標題 Regex:").pack(side=tk.LEFT, padx=3)
    title_var = tk.StringVar(value="")
    title_entry = ttk.Entry(top_bar, textvariable=title_var, width=24)
    title_entry.pack(side=tk.LEFT, padx=3)

    status_var = tk.StringVar(value="請輸入視窗 Regex 並點擊「抓一張」，或載入現有 preset。")

    def on_grab() -> None:
        nonlocal current_image_bgr
        regex_val = title_var.get().strip() or None
        status_var.set(f"正在擷取視窗 [{regex_val or '當前前景'}] ...")
        win.update_idletasks()
        try:
            with CaptureSession(window_title_regex=regex_val) as cap:
                bgr = cap.grab()
                current_image_bgr = bgr
                h, w = bgr.shape[:2]
                status_var.set(f"擷取成功: {w}x{h} px")
                redraw_canvas()
        except Exception as err:
            logger.exception("Capture error")
            status_var.set(f"擷取失敗: {err}")
            messagebox.showerror("擷取錯誤", str(err), parent=win)

    btn_grab = ttk.Button(top_bar, text="抓一張 (Capture)", command=on_grab)
    btn_grab.pack(side=tk.LEFT, padx=5)

    ttk.Label(top_bar, text="Preset ID:").pack(side=tk.LEFT, padx=(15, 3))
    preset_id_var = tk.StringVar(value="my-game")
    ttk.Entry(top_bar, textvariable=preset_id_var, width=12).pack(side=tk.LEFT, padx=3)

    ttk.Label(top_bar, text="名稱:").pack(side=tk.LEFT, padx=3)
    preset_name_var = tk.StringVar(value="My Game")
    ttk.Entry(top_bar, textvariable=preset_name_var, width=12).pack(side=tk.LEFT, padx=3)

    ttk.Label(top_bar, text="類型:").pack(side=tk.LEFT, padx=3)
    game_type_var = tk.StringVar(value="fps")
    type_cb = ttk.Combobox(top_bar, textvariable=game_type_var, values=["fps", "rts", "moba", "demo", "generic"], width=7)
    type_cb.pack(side=tk.LEFT, padx=3)

    ttk.Label(top_bar, text="全域靈敏度:").pack(side=tk.LEFT, padx=3)
    sens_var = tk.DoubleVar(value=1.0)
    sens_spin = ttk.Spinbox(top_bar, from_=0.25, to=4.0, increment=0.05, textvariable=sens_var, width=5)
    sens_spin.pack(side=tk.LEFT, padx=3)

    # Main split container
    main_frame = ttk.Frame(win)
    main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=4)

    # Left: Canvas
    canvas_frame = ttk.Frame(main_frame)
    canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(canvas_frame, bg="#202020", cursor="cross")
    canvas.pack(fill=tk.BOTH, expand=True)

    # Right: Regions Sidebar
    sidebar = ttk.Frame(main_frame, width=320, padding=6)
    sidebar.pack(side=tk.RIGHT, fill=tk.Y)
    sidebar.pack_propagate(False)

    ttk.Label(sidebar, text="已設定區域 (Regions)", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

    region_listbox = tk.Listbox(sidebar, height=8, selectmode=tk.SINGLE)
    region_listbox.pack(fill=tk.X, pady=(0, 6))

    # Form to inspect / edit selected region
    edit_frame = ttk.LabelFrame(sidebar, text="區域細節編輯", padding=6)
    edit_frame.pack(fill=tk.X, pady=(0, 6))

    r_name_var = tk.StringVar()
    ttk.Label(edit_frame, text="區域名稱:").grid(row=0, column=0, sticky=tk.W, pady=2)
    r_name_entry = ttk.Entry(edit_frame, textvariable=r_name_var)
    r_name_entry.grid(row=0, column=1, sticky=tk.EW, pady=2)

    r_rect_var = tk.StringVar()
    ttk.Label(edit_frame, text="座標 (0-1):").grid(row=1, column=0, sticky=tk.W, pady=2)
    r_rect_entry = ttk.Entry(edit_frame, textvariable=r_rect_var)
    r_rect_entry.grid(row=1, column=1, sticky=tk.EW, pady=2)

    r_interval_var = tk.IntVar(value=300)
    ttk.Label(edit_frame, text="偵測間隔 ms:").grid(row=2, column=0, sticky=tk.W, pady=2)
    r_interval_entry = ttk.Entry(edit_frame, textvariable=r_interval_var)
    r_interval_entry.grid(row=2, column=1, sticky=tk.EW, pady=2)

    r_rule_type_var = tk.StringVar(value="change")
    ttk.Label(edit_frame, text="規則類型:").grid(row=3, column=0, sticky=tk.W, pady=2)
    rule_cb = ttk.Combobox(
        edit_frame,
        textvariable=r_rule_type_var,
        values=["change", "color_ratio", "blob_count", "luma_sat_drop", "template"],
        state="readonly",
    )
    rule_cb.grid(row=3, column=1, sticky=tk.EW, pady=2)

    r_rule_sens_var = tk.StringVar(value="")
    ttk.Label(edit_frame, text="局部靈敏度:").grid(row=4, column=0, sticky=tk.W, pady=2)
    r_rule_sens_entry = ttk.Entry(edit_frame, textvariable=r_rule_sens_var)
    r_rule_sens_entry.grid(row=4, column=1, sticky=tk.EW, pady=2)

    r_rule_extra_var = tk.StringVar(value="{}")
    ttk.Label(edit_frame, text="規則參數(JSON):").grid(row=5, column=0, sticky=tk.W, pady=2)
    r_rule_extra_entry = ttk.Entry(edit_frame, textvariable=r_rule_extra_var)
    r_rule_extra_entry.grid(row=5, column=1, sticky=tk.EW, pady=2)

    edit_frame.columnconfigure(1, weight=1)

    def refresh_region_listbox() -> None:
        region_listbox.delete(0, tk.END)
        for r in regions_data:
            rect = r.get("rect", [0, 0, 0, 0])
            rtype = r.get("rule", {}).get("type", "change")
            region_listbox.insert(tk.END, f"{r['name']} ({rtype}) [{rect[0]:.2f},{rect[1]:.2f}]")

    def on_region_select(event: Any = None) -> None:
        idxs = region_listbox.curselection()
        if not idxs:
            return
        idx = idxs[0]
        r = regions_data[idx]
        r_name_var.set(r.get("name", ""))
        r_rect_var.set(str(r.get("rect", [0, 0, 0, 0])))
        r_interval_var.set(int(r.get("interval_ms", 300)))
        rule = r.get("rule", {})
        r_rule_type_var.set(rule.get("type", "change"))
        r_rule_sens_var.set(str(rule.get("sensitivity", "")))

        # Rule extra params excluding type & sensitivity
        extras = {k: v for k, v in rule.items() if k not in ("type", "sensitivity")}
        r_rule_extra_var.set(json.dumps(extras, ensure_ascii=False))

        redraw_canvas()

    region_listbox.bind("<<ListboxSelect>>", on_region_select)

    def on_apply_edit() -> None:
        idxs = region_listbox.curselection()
        if not idxs:
            return
        idx = idxs[0]
        new_name = r_name_var.get().strip() or f"region_{idx+1}"
        try:
            rect_raw = json.loads(r_rect_var.get())
            if not isinstance(rect_raw, (list, tuple)) or len(rect_raw) != 4:
                raise ValueError("rect 必須是 4 個數字 [x, y, w, h]")
            rect = [float(x) for x in rect_raw]
        except Exception as e:
            messagebox.showerror("座標格式錯誤", f"請輸入合法的 [x, y, w, h] 陣列: {e}", parent=win)
            return

        rule_dict: Dict[str, Any] = {"type": r_rule_type_var.get()}
        sens_str = r_rule_sens_var.get().strip()
        if sens_str:
            try:
                rule_dict["sensitivity"] = float(sens_str)
            except ValueError:
                pass

        try:
            extras = json.loads(r_rule_extra_var.get() or "{}")
            if isinstance(extras, dict):
                rule_dict.update(extras)
        except Exception as e:
            messagebox.showwarning("參數警告", f"規則參數 JSON 解析失敗，將忽略額外參數: {e}", parent=win)

        regions_data[idx] = {
            "name": new_name,
            "rect": rect,
            "interval_ms": max(10, r_interval_var.get()),
            "rule": rule_dict,
        }
        refresh_region_listbox()
        region_listbox.select_set(idx)
        redraw_canvas()
        status_var.set(f"已更新區域: {new_name}")

    btn_apply = ttk.Button(edit_frame, text="更新當前區域", command=on_apply_edit)
    btn_apply.grid(row=6, column=0, columnspan=2, pady=4, sticky=tk.EW)

    def on_delete_region() -> None:
        idxs = region_listbox.curselection()
        if not idxs:
            return
        idx = idxs[0]
        removed = regions_data.pop(idx)
        refresh_region_listbox()
        redraw_canvas()
        status_var.set(f"已刪除區域: {removed.get('name')}")

    btn_delete = ttk.Button(sidebar, text="刪除選取區域", command=on_delete_region)
    btn_delete.pack(fill=tk.X, pady=(0, 6))

    # Save & Load Preset Buttons
    def on_load_preset(preset_file: Optional[Path] = None) -> None:
        nonlocal regions_data
        if preset_file is None:
            from tkinter import filedialog
            chosen = filedialog.askopenfilename(
                title="載入 Preset JSON",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                parent=win,
            )
            if not chosen:
                return
            p = Path(chosen)
        else:
            p = Path(preset_file)

        try:
            loaded = load_preset(p)
            preset_id_var.set(loaded.id)
            preset_name_var.set(loaded.name)
            game_type_var.set(loaded.game_type)
            sens_var.set(loaded.sensitivity)
            title_var.set(str(loaded.match.get("window_title_regex", "")))

            regions_data.clear()
            for r in loaded.regions:
                regions_data.append({
                    "name": r.name,
                    "rect": list(r.rect),
                    "interval_ms": r.interval_ms,
                    "rule": dict(r.rule),
                })
            refresh_region_listbox()
            redraw_canvas()
            status_var.set(f"已成功載入 Preset: {p.name}")
        except Exception as e:
            logger.exception("Failed to load preset")
            messagebox.showerror("載入失敗", f"無法載入 Preset: {e}", parent=win)

    def on_save_preset() -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="儲存 Preset JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            parent=win,
        )
        if not path:
            return

        ref_aspect = 1.7778
        if current_image_bgr is not None:
            h, w = current_image_bgr.shape[:2]
            if h > 0:
                ref_aspect = round(w / h, 4)

        data = build_preset(
            preset_id=preset_id_var.get(),
            name=preset_name_var.get(),
            window_title_regex=title_var.get(),
            reference_aspect=ref_aspect,
            game_type=game_type_var.get(),
            enabled=True,
            sensitivity=sens_var.get(),
            regions=regions_data,
        )
        try:
            saved = save_preset(data, path)
            status_var.set(f"Preset 已儲存至: {saved.name}")
            messagebox.showinfo("儲存成功", f"Preset 已成功儲存至:\n{saved}", parent=win)
        except Exception as e:
            logger.exception("Failed to save preset")
            messagebox.showerror("儲存失敗", f"儲存錯誤: {e}", parent=win)

    btn_load = ttk.Button(sidebar, text="載入現有 Preset...", command=lambda: on_load_preset(None))
    btn_load.pack(fill=tk.X, pady=(0, 4))

    btn_save = ttk.Button(sidebar, text="儲存 Preset JSON...", command=on_save_preset)
    btn_save.pack(fill=tk.X, pady=(0, 4))

    # Canvas Rendering & Drag events
    def redraw_canvas() -> None:
        nonlocal current_image_tk, display_scale, display_offset_x, display_offset_y
        canvas.delete("all")
        c_w = canvas.winfo_width()
        c_h = canvas.winfo_height()
        if c_w <= 1 or c_h <= 1:
            c_w = 700
            c_h = 500

        if current_image_bgr is None:
            canvas.create_text(
                c_w // 2,
                c_h // 2,
                text="尚無擷取畫面\n請在上方輸入視窗標題 Regex 並點擊「抓一張」",
                fill="#888888",
                justify=tk.CENTER,
                font=("TkDefaultFont", 12),
            )
            return

        img_h, img_w = current_image_bgr.shape[:2]
        scale_w = c_w / img_w
        scale_h = c_h / img_h
        display_scale = min(scale_w, scale_h, 1.0)
        disp_w = int(img_w * display_scale)
        disp_h = int(img_h * display_scale)
        display_offset_x = max(0, (c_w - disp_w) // 2)
        display_offset_y = max(0, (c_h - disp_h) // 2)

        # Convert BGR to RGB for PIL
        rgb = cv2.cvtColor(current_image_bgr, cv2.COLOR_BGR2RGB)
        if display_scale < 1.0:
            resized = cv2.resize(rgb, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
        else:
            resized = rgb

        pil_img = Image.fromarray(resized)
        current_image_tk = ImageTk.PhotoImage(pil_img)
        canvas.create_image(
            display_offset_x,
            display_offset_y,
            anchor=tk.NW,
            image=current_image_tk,
        )

        # Draw existing regions
        selected_indices = region_listbox.curselection()
        selected_idx = selected_indices[0] if selected_indices else -1

        for idx, r in enumerate(regions_data):
            rect = r.get("rect", [0, 0, 0, 0])
            nx, ny, nw, nh = rect
            px = display_offset_x + int(nx * disp_w)
            py = display_offset_y + int(ny * disp_h)
            pw = int(nw * disp_w)
            ph = int(nh * disp_h)

            is_sel = idx == selected_idx
            outline_color = "#00FF00" if not is_sel else "#FF3333"
            line_width = 2 if not is_sel else 3

            canvas.create_rectangle(
                px, py, px + pw, py + ph,
                outline=outline_color,
                width=line_width,
                tags=f"region_{idx}",
            )
            canvas.create_text(
                px + 3,
                max(display_offset_y, py - 12),
                text=r.get("name", ""),
                anchor=tk.NW,
                fill=outline_color,
                font=("TkDefaultFont", 9, "bold"),
            )

    canvas.bind("<Configure>", lambda e: redraw_canvas())

    def on_canvas_press(event: Any) -> None:
        nonlocal drag_start, current_rect_item
        if current_image_bgr is None:
            return
        drag_start = (event.x, event.y)
        if current_rect_item is not None:
            canvas.delete(current_rect_item)
        current_rect_item = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#FFD700", width=2, dash=(4, 4)
        )

    def on_canvas_drag(event: Any) -> None:
        nonlocal current_rect_item
        if drag_start is None or current_rect_item is None:
            return
        canvas.coords(current_rect_item, drag_start[0], drag_start[1], event.x, event.y)

    def on_canvas_release(event: Any) -> None:
        nonlocal drag_start, current_rect_item
        if drag_start is None or current_image_bgr is None:
            return

        x1, y1 = drag_start
        x2, y2 = event.x, event.y
        drag_start = None
        if current_rect_item is not None:
            canvas.delete(current_rect_item)
            current_rect_item = None

        img_h, img_w = current_image_bgr.shape[:2]
        disp_w = int(img_w * display_scale)
        disp_h = int(img_h * display_scale)

        # Convert canvas coords to displayed image coords
        ix1 = x1 - display_offset_x
        iy1 = y1 - display_offset_y
        ix2 = x2 - display_offset_x
        iy2 = y2 - display_offset_y

        if disp_w <= 0 or disp_h <= 0:
            return

        nx, ny, nw, nh = normalize_rect(ix1, iy1, ix2, iy2, disp_w, disp_h)

        # If drag was essentially a zero-click, ignore
        if nw * disp_w < 4 and nh * disp_h < 4:
            return

        # Prompt for region name
        default_name = f"region_{len(regions_data) + 1}"
        region_name = simpledialog.askstring(
            "新區域",
            f"請輸入區域名稱:\n(座標: [{nx:.3f}, {ny:.3f}, {nw:.3f}, {nh:.3f}])",
            initialvalue=default_name,
            parent=win,
        )
        if not region_name or not region_name.strip():
            return

        new_region = {
            "name": region_name.strip(),
            "rect": [nx, ny, nw, nh],
            "interval_ms": 300,
            "rule": {"type": "change"},
        }
        regions_data.append(new_region)
        refresh_region_listbox()
        region_listbox.selection_clear(0, tk.END)
        region_listbox.selection_set(len(regions_data) - 1)
        on_region_select()
        redraw_canvas()
        status_var.set(f"新增區域: {region_name}")

    canvas.bind("<ButtonPress-1>", on_canvas_press)
    canvas.bind("<B1-Motion>", on_canvas_drag)
    canvas.bind("<ButtonRelease-1>", on_canvas_release)

    # Status Bar
    status_bar = ttk.Label(win, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W, padding=3)
    status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # If preset_path provided initially, load it
    if preset_path is not None:
        p = Path(preset_path)
        if p.is_file():
            on_load_preset(p)

    def on_close() -> None:
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    # If this wizard created the main root window, start mainloop
    if created_root:
        root.mainloop()


if __name__ == "__main__":
    run_editor()
