"""視覺處理模組：合圖、預算節流、視覺呼叫。

包含：
1. compose_frame: 依據主畫面與指定 ROI 產生合成圖（縮圖/標籤貼在右側或下方）。
2. VisionBudget: 分/時雙層次預算控制與節流（monotonic 時間）。
3. Eye: 封裝 VisionClient 呼叫，提供安全例外捕獲與預算檢查。
"""

from __future__ import annotations

import collections
import logging
import time
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from .capture import crop_norm

logger = logging.getLogger(__name__)

DEFAULT_VISION_PROMPT = (
    "用一句話描述這個遊戲畫面的重點（你在幹嘛、有沒有危險）。不要編看不到的東西。"
)


def _encode_jpeg_limited(
    img: np.ndarray, quality: int, max_bytes: int
) -> bytes:
    """JPEG 超過上限就縮圖／降品質重編，避免 vision API 擋大圖。"""
    scale = 1.0
    q = int(quality)
    while True:
        ok, encoded = cv2.imencode(
            ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), q]
        )
        if not ok:
            raise RuntimeError("cv2.imencode 失敗")
        data = encoded.tobytes()
        if len(data) <= max_bytes or scale <= 0.35:
            return data
        scale *= 0.85
        q = max(50, q - 5)
        img = cv2.resize(
            img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )


def compose_frame(
    full_bgr: np.ndarray,
    regions: Optional[List[Tuple[str, Tuple[float, float, float, float]]]] = None,
    max_width: int = 1280,
    jpeg_quality: int = 80,
    max_bytes: int = 4_500_000,
) -> bytes:
    """將遊戲主畫面縮放並與各 ROI 裁切合成一張圖，輸出 JPEG bytes。

    Args:
        full_bgr: 主畫面 BGR 影像 (H, W, 3)。
        regions: [(name, (x, y, w, h)), ...] 正規化 (0.0~1.0) 座標清單。
        max_width: 主畫面縮放後的最大寬度。
        jpeg_quality: JPEG 壓縮品質（預設 80）。

    Returns:
        JPEG 編碼的 bytes。
    """
    if full_bgr is None or full_bgr.size == 0:
        raise ValueError("full_bgr 不能為空")

    h, w = full_bgr.shape[:2]
    if w > max_width:
        scale = max_width / float(w)
        target_w = max_width
        target_h = max(1, int(round(h * scale)))
        main_img = cv2.resize(full_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
    else:
        main_img = full_bgr.copy()

    # 如果沒有 regions 或 regions 為空，直接編碼主畫面
    if not regions:
        return _encode_jpeg_limited(main_img, jpeg_quality, max_bytes)

    main_h, main_w = main_img.shape[:2]

    # 製作 ROI 縮圖區塊
    roi_blocks = []
    # 決定側邊欄寬度（約佔主畫面寬度的 25%~35%，至少 160px，不超過 360px）
    roi_target_w = max(160, min(360, int(main_w * 0.3)))

    for name, rect_norm in regions:
        cropped = crop_norm(full_bgr, rect_norm)
        ch, cw = cropped.shape[:2]
        if cw <= 0 or ch <= 0:
            continue

        # 縮放到固定寬度 roi_target_w
        roi_scale = roi_target_w / float(cw)
        roi_h = max(1, int(round(ch * roi_scale)))
        resized_roi = cv2.resize(cropped, (roi_target_w, roi_h), interpolation=cv2.INTER_AREA)

        # 加上上方標籤欄（高 24px，黑色底白色字）
        label_bar_h = 24
        labeled_block = np.zeros((roi_h + label_bar_h, roi_target_w, 3), dtype=np.uint8)
        # 背景填暗灰色 (30, 30, 30)
        labeled_block[:label_bar_h, :] = (30, 30, 30)
        # 標籤文字
        cv2.putText(
            labeled_block,
            str(name),
            (6, 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        # 貼上 ROI 縮圖
        labeled_block[label_bar_h:, :] = resized_roi

        # 外框 (1px 白色或淺灰)
        cv2.rectangle(
            labeled_block,
            (0, 0),
            (roi_target_w - 1, roi_h + label_bar_h - 1),
            (80, 80, 80),
            1,
        )
        roi_blocks.append(labeled_block)

    if not roi_blocks:
        return _encode_jpeg_limited(main_img, jpeg_quality, max_bytes)

    total_roi_h = sum(b.shape[0] for b in roi_blocks) + (len(roi_blocks) - 1) * 8

    # 決定版面：若 ROI 總高度合理（不超過 main_h * 1.5），貼在右側；否則拼在下方
    if total_roi_h <= main_h * 1.5:
        # 貼右側
        combined_w = main_w + roi_target_w + 12
        combined_h = max(main_h, total_roi_h + 16)
        canvas = np.zeros((combined_h, combined_w, 3), dtype=np.uint8)
        canvas[:main_h, :main_w] = main_img

        y_offset = 8
        x_offset = main_w + 8
        for b in roi_blocks:
            bh, bw = b.shape[:2]
            canvas[y_offset : y_offset + bh, x_offset : x_offset + bw] = b
            y_offset += bh + 8
    else:
        # 貼下方（橫向排列）：寬度要把每塊之間的 8px 間距算進去，不然會越界。
        combined_w = max(
            main_w, sum(b.shape[1] for b in roi_blocks) + 8 * (len(roi_blocks) + 1)
        )
        max_b_h = max(b.shape[0] for b in roi_blocks)
        combined_h = main_h + max_b_h + 16
        canvas = np.zeros((combined_h, combined_w, 3), dtype=np.uint8)
        canvas[:main_h, :main_w] = main_img

        x_offset = 8
        y_offset = main_h + 8
        for b in roi_blocks:
            bh, bw = b.shape[:2]
            canvas[y_offset : y_offset + bh, x_offset : x_offset + bw] = b
            x_offset += bw + 8

    return _encode_jpeg_limited(canvas, jpeg_quality, max_bytes)


class VisionBudget:
    """視覺預算控制：雙滑動視窗（每分鐘 / 每小時上限）。"""

    def __init__(self, max_per_minute: int = 4, max_per_hour: int = 60) -> None:
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self._minute_calls: collections.deque[float] = collections.deque()
        self._hour_calls: collections.deque[float] = collections.deque()

    def _cleanup(self, t: float) -> None:
        minute_cutoff = t - 60.0
        hour_cutoff = t - 3600.0
        while self._minute_calls and self._minute_calls[0] <= minute_cutoff:
            self._minute_calls.popleft()
        while self._hour_calls and self._hour_calls[0] <= hour_cutoff:
            self._hour_calls.popleft()

    def allow(self, now: Optional[float] = None) -> bool:
        """檢查當前時刻是否還有可用額度。"""
        t = time.monotonic() if now is None else now
        self._cleanup(t)
        if len(self._minute_calls) >= self.max_per_minute:
            return False
        if len(self._hour_calls) >= self.max_per_hour:
            return False
        return True

    def spend(self, now: Optional[float] = None) -> bool:
        """消耗一次預算。若已達上限則回傳 False 且不記錄。"""
        t = time.monotonic() if now is None else now
        self._cleanup(t)
        if len(self._minute_calls) >= self.max_per_minute:
            return False
        if len(self._hour_calls) >= self.max_per_hour:
            return False
        self._minute_calls.append(t)
        self._hour_calls.append(t)
        return True

    def reset(self) -> None:
        """清空所有呼叫記錄。"""
        self._minute_calls.clear()
        self._hour_calls.clear()


class Eye:
    """眼睛：封裝合圖、預算節流、視覺模型描述呼叫。"""

    def __init__(
        self,
        client: Any,
        budget: Optional[VisionBudget] = None,
        prompt: Optional[str] = None,
    ) -> None:
        self.client = client
        self.budget = budget if budget is not None else VisionBudget()
        self.prompt = prompt or DEFAULT_VISION_PROMPT
        self.last_error: Optional[str] = None

    def describe(
        self,
        full_bgr: np.ndarray,
        regions: Optional[List[Tuple[str, Tuple[float, float, float, float]]]] = None,
        now: Optional[float] = None,
    ) -> Optional[str]:
        """產出畫面描述。

        - 預算不足回 None（不消耗、不呼叫 client）。
        - 呼叫失敗回 None 並記 last_error。
        """
        self.last_error = None

        if not self.budget.allow(now=now):
            logger.debug("Vision budget exceeded, skipping describe call")
            return None

        try:
            image_bytes = compose_frame(full_bgr, regions=regions)
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"compose_frame error: {exc}"
            logger.warning(self.last_error)
            return None

        # 消耗預算
        if not self.budget.spend(now=now):
            return None

        try:
            result = self.client.describe(image_bytes, self.prompt)
            return result
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"Vision client error: {exc}"
            logger.warning(self.last_error)
            return None
