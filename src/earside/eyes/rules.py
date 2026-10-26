"""Sentinel rule engine and detectors for screen regions."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from earside.eyes.preset import Preset, Region


def _clamp_sens(value: float) -> float:
    return max(0.25, min(4.0, float(value)))


def _easier_upper(base: float, sens: float) -> float:
    """門檻越接近 1 越容易觸發（luma/sat 的比值）。"""
    return max(0.0, min(1.0, 1.0 - (1.0 - float(base)) / _clamp_sens(sens)))


def _easier_lower(base: float, sens: float) -> float:
    """門檻越低越容易觸發（diff/min_ratio/template）。"""
    return max(0.0, min(1.0, float(base) / _clamp_sens(sens)))


class RegionState:
    """State tracking for a single region (history deque for temporal smoothing and baseline)."""

    def __init__(self, region: Region, base_dir: Optional[Path] = None):
        self.region = region
        self.base_dir = base_dir
        # Store recent (timestamp_ms, R, S) or metrics for baselines
        # We need at least 10s of history. With interval_ms, calculate maxlen.
        # Max history: 15s to be safe, minimum 50 entries
        interval = max(region.interval_ms, 50)
        max_samples = max(int(15000 / interval), 100)
        self.history: deque[Tuple[float, float, float]] = deque(maxlen=max_samples)

        # Recent raw metrics for temporal smoothing; preset 可用 median_frames 調快慢
        median_frames = max(1, int(region.rule.get("median_frames", 5)))
        self.recent_metrics: deque[Dict[str, float]] = deque(maxlen=median_frames)

        # Previous frame for 'change' detector (grayscale, small size)
        self.prev_frame_gray: Optional[np.ndarray] = None

        # Consecutive active frame counter
        self.consecutive_active: int = 0

        # Cached template if applicable
        self._cached_template: Optional[np.ndarray] = None
        self._cached_template_path: Optional[str] = None


class RuleEngine:
    """Evaluates regions against configured sentinel rules with temporal filtering."""

    def __init__(self, preset: Preset, sensitivity: float | None = None):
        self.preset = preset
        self.base_sensitivity = _clamp_sens(
            sensitivity if sensitivity is not None else getattr(preset, "sensitivity", 1.0)
        )
        self.states: Dict[str, RegionState] = {
            r.name: RegionState(r, preset.base_dir) for r in preset.regions
        }

    def reset(self, region_name: Optional[str] = None):
        """Reset state for a specific region or all regions."""
        if region_name:
            if region_name in self.states:
                self.states[region_name] = RegionState(
                    self.states[region_name].region, self.preset.base_dir
                )
        else:
            self.states = {
                r.name: RegionState(r, self.preset.base_dir) for r in self.preset.regions
            }

    def evaluate(
        self,
        region_name: str,
        frame_bgr: np.ndarray,
        timestamp_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Evaluate a screen region frame.

        Args:
            region_name: The region identifier defined in preset.
            frame_bgr: BGR ndarray cropped for this region.
            timestamp_ms: Optional timestamp in milliseconds. If omitted, synthesized.

        Returns:
            {"region": region_name, "on": bool, "score": float, "metrics": dict}
        """
        if region_name not in self.states:
            raise KeyError(f"Region '{region_name}' not defined in preset")

        state = self.states[region_name]
        rule = state.region.rule
        rule_type = rule.get("type")

        if frame_bgr is None or frame_bgr.size == 0:
            return {
                "region": region_name,
                "on": False,
                "score": 0.0,
                "metrics": {"error": "empty_frame"},
            }

        # Dispatch rule execution
        if rule_type == "luma_sat_drop":
            res = self._eval_luma_sat_drop(state, frame_bgr, timestamp_ms)
        elif rule_type == "color_ratio":
            res = self._eval_color_ratio(state, frame_bgr)
        elif rule_type == "blob_count":
            res = self._eval_blob_count(state, frame_bgr)
        elif rule_type == "template":
            res = self._eval_template(state, frame_bgr)
        elif rule_type == "change":
            res = self._eval_change(state, frame_bgr)
        elif rule_type == "ocr_contains":
            res = {
                "raw_on": False,
                "score": 0.0,
                "metrics": {"reason": "ocr not implemented"},
            }
        else:
            raise ValueError(f"Unknown rule type: '{rule_type}'")

        # Temporal consecutive check
        raw_on = res.get("raw_on", False)
        consecutive_target = int(rule.get("consecutive", 1))

        if raw_on:
            state.consecutive_active += 1
        else:
            state.consecutive_active = 0

        final_on = state.consecutive_active >= consecutive_target

        return {
            "region": region_name,
            "on": final_on,
            "score": float(np.clip(res.get("score", 0.0), 0.0, 1.0)),
            "metrics": res.get("metrics", {}),
        }

    # -------------------------------------------------------------------------
    # Rule implementations
    # -------------------------------------------------------------------------

    def _eval_luma_sat_drop(
        self, state: RegionState, frame_bgr: np.ndarray, timestamp_ms: Optional[float]
    ) -> Dict[str, Any]:
        """Calculates L_target / L_bg ratio R and saturation S, compares against sliding median baseline R0, S0."""
        rule = state.region.rule
        sens = _clamp_sens(rule.get("sensitivity", self.base_sensitivity))
        bg_ring_ratio = float(rule.get("bg_ring", 0.05))
        luma_ratio_thresh = _easier_upper(rule.get("luma_ratio", 0.6), sens)
        sat_ratio_thresh = _easier_upper(rule.get("sat_ratio", 0.5), sens)

        h, w = frame_bgr.shape[:2]
        ring_px_x = max(1, int(round(w * bg_ring_ratio)))
        ring_px_y = max(1, int(round(h * bg_ring_ratio)))

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]

        # Inner target area
        x1, y1 = ring_px_x, ring_px_y
        x2, y2 = max(x1 + 1, w - ring_px_x), max(y1 + 1, h - ring_px_y)

        target_gray = gray[y1:y2, x1:x2]
        target_sat = sat[y1:y2, x1:x2]

        l_target = float(np.mean(target_gray)) if target_gray.size > 0 else 0.0
        s_val = float(np.mean(target_sat)) if target_sat.size > 0 else 0.0

        # Ring background area (mask)
        mask = np.ones((h, w), dtype=bool)
        mask[y1:y2, x1:x2] = False
        ring_gray = gray[mask]
        l_bg = float(np.mean(ring_gray)) if ring_gray.size > 0 else 0.0

        # Relative brightness ratio R
        # Avoid division by zero with small epsilon
        eps = 1e-4
        r_val = float(l_target / (l_bg + eps))

        # Temporal smoothing: store raw (r_val, s_val) in recent_metrics (5-frame)
        state.recent_metrics.append({"r": r_val, "s": s_val})
        r_smoothed = float(np.median([m["r"] for m in state.recent_metrics]))
        s_smoothed = float(np.median([m["s"] for m in state.recent_metrics]))

        # Track history for sliding baseline R0, S0
        # If timestamp_ms is not provided, use simulated step from interval_ms
        if timestamp_ms is None:
            if state.history:
                last_t = state.history[-1][0]
                t_now = last_t + state.region.interval_ms
            else:
                t_now = 0.0
        else:
            t_now = float(timestamp_ms)

        state.history.append((t_now, r_smoothed, s_smoothed))

        # Baseline R0, S0: sliding median from history, EXCLUDING the recent 2 seconds (2000 ms)
        # Plan specifies: "排除最近 2 秒（用 interval_ms 換算要排除幾筆；至少保留 5 筆才開始判斷）"
        # We can calculate based on timestamps or index count. Using interval_ms:
        exclude_count = max(1, int(round(2000.0 / max(state.region.interval_ms, 1))))

        if len(state.history) > exclude_count:
            baseline_slice = list(state.history)[:-exclude_count]
        else:
            baseline_slice = []

        metrics: Dict[str, Any] = {
            "l_target": round(l_target, 2),
            "l_bg": round(l_bg, 2),
            "r": round(r_smoothed, 4),
            "s": round(s_smoothed, 2),
            "history_len": len(state.history),
            "baseline_count": len(baseline_slice),
        }

        # Need at least 5 baseline samples to judge
        if len(baseline_slice) < 5:
            metrics["reason"] = "warmup_baseline"
            return {"raw_on": False, "score": 0.0, "metrics": metrics}

        r0 = float(np.median([b[1] for b in baseline_slice]))
        s0 = float(np.median([b[2] for b in baseline_slice]))
        metrics["r0"] = round(r0, 4)
        metrics["s0"] = round(s0, 2)

        # Condition: R < R0 * luma_ratio and S < S0 * sat_ratio
        # Avoid division by zero if r0 or s0 is tiny
        r_thresh = r0 * luma_ratio_thresh
        s_thresh = s0 * sat_ratio_thresh

        cond_r = r_smoothed < r_thresh
        cond_s = s_smoothed < s_thresh

        is_on = cond_r and cond_s

        # Score calculation: how far below the thresholds
        # score = 1.0 when r=0, s=0; score ~ 0.5 at threshold
        score_r = max(0.0, 1.0 - (r_smoothed / (r0 + eps))) if r0 > 0 else 0.0
        score_s = max(0.0, 1.0 - (s_smoothed / (s0 + eps))) if s0 > 0 else 0.0
        score = (score_r + score_s) / 2.0

        metrics["r_thresh"] = round(r_thresh, 4)
        metrics["s_thresh"] = round(s_thresh, 2)

        return {"raw_on": is_on, "score": score, "metrics": metrics}

    def _eval_color_ratio(self, state: RegionState, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """HSV range pixel ratio >= min_ratio."""
        rule = state.region.rule
        hsv_range = rule.get("hsv")
        sens = _clamp_sens(rule.get("sensitivity", self.base_sensitivity))
        min_ratio = _easier_lower(rule.get("min_ratio", 0.1), sens)

        if not hsv_range or len(hsv_range) != 6:
            raise ValueError(
                f"Rule 'color_ratio' requires 'hsv' with 6 integers [h_min, h_max, s_min, s_max, v_min, v_max], got {hsv_range}"
            )

        h_min, h_max, s_min, s_max, v_min, v_max = [int(v) for v in hsv_range]
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

        # Handle hue wrap-around (e.g. red around 0 and 180) if h_min > h_max
        if h_min > h_max:
            lower1 = np.array([h_min, s_min, v_min], dtype=np.uint8)
            upper1 = np.array([180, s_max, v_max], dtype=np.uint8)
            lower2 = np.array([0, s_min, v_min], dtype=np.uint8)
            upper2 = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.bitwise_or(
                cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2)
            )
        else:
            lower = np.array([h_min, s_min, v_min], dtype=np.uint8)
            upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)

        total_pixels = frame_bgr.shape[0] * frame_bgr.shape[1]
        matched_pixels = int(cv2.countNonZero(mask))
        ratio = float(matched_pixels / total_pixels) if total_pixels > 0 else 0.0

        is_on = ratio >= min_ratio
        # Score normalized to ratio relative to min_ratio
        score = min(1.0, ratio / min_ratio) if min_ratio > 0 else (1.0 if ratio > 0 else 0.0)

        metrics = {
            "matched_ratio": round(ratio, 4),
            "matched_pixels": matched_pixels,
            "min_ratio": min_ratio,
        }
        return {"raw_on": is_on, "score": score, "metrics": metrics}

    def _eval_blob_count(self, state: RegionState, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """HSV mask -> cv2.connectedComponentsWithStats -> count blobs in area range and center_near."""
        rule = state.region.rule
        hsv_range = rule.get("hsv")
        sens = _clamp_sens(rule.get("sensitivity", self.base_sensitivity))
        min_area = int(rule.get("min_area_px", 1))
        max_area = int(rule.get("max_area_px", 1000000))
        center_near = rule.get("center_near")
        min_count = max(
            1, int(round(int(rule.get("min_count", 1)) / sens))
        )  # 靈敏度高→需要的 blob 數變少

        if not hsv_range or len(hsv_range) != 6:
            raise ValueError(
                f"Rule 'blob_count' requires 'hsv' with 6 integers [h_min, h_max, s_min, s_max, v_min, v_max], got {hsv_range}"
            )

        h_min, h_max, s_min, s_max, v_min, v_max = [int(v) for v in hsv_range]
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

        if h_min > h_max:
            lower1 = np.array([h_min, s_min, v_min], dtype=np.uint8)
            upper1 = np.array([180, s_max, v_max], dtype=np.uint8)
            lower2 = np.array([0, s_min, v_min], dtype=np.uint8)
            upper2 = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.bitwise_or(
                cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2)
            )
        else:
            lower = np.array([h_min, s_min, v_min], dtype=np.uint8)
            upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)

        h, w = frame_bgr.shape[:2]
        center_x = (w - 1) / 2.0
        center_y = (h - 1) / 2.0
        diag = np.hypot(w, h)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )

        matched_blobs = 0
        min_center_dist_norm = 1.0

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if min_area <= area <= max_area:
                cx, cy = centroids[i]
                # Normalized distance to center: 0 (center) to 1 (corner)
                dist_px = np.hypot(cx - center_x, cy - center_y)
                # Normalization factor: half diagonal so corner is ~1.0
                dist_norm = float(dist_px / (diag / 2.0 + 1e-6))
                dist_norm = min(1.0, dist_norm)

                if dist_norm < min_center_dist_norm:
                    min_center_dist_norm = dist_norm

                if center_near is not None:
                    if dist_norm <= float(center_near):
                        matched_blobs += 1
                else:
                    matched_blobs += 1

        is_on = matched_blobs >= min_count
        score = min(1.0, float(matched_blobs) / float(min_count)) if min_count > 0 else 1.0

        metrics = {
            "blob_count": matched_blobs,
            "min_count": min_count,
            "min_center_dist": round(min_center_dist_norm, 4),
        }
        return {"raw_on": is_on, "score": score, "metrics": metrics}

    def _eval_template(self, state: RegionState, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """cv2.matchTemplate max_val >= threshold."""
        rule = state.region.rule
        template_rel_path = rule.get("template")
        sens = _clamp_sens(rule.get("sensitivity", self.base_sensitivity))
        threshold = _easier_lower(rule.get("threshold", 0.8), sens)

        if not template_rel_path:
            raise ValueError("Rule 'template' missing 'template' path")

        # Resolve path relative to preset base_dir
        if state._cached_template is None or state._cached_template_path != template_rel_path:
            if state.base_dir:
                tpl_path = (state.base_dir / template_rel_path).resolve()
            else:
                tpl_path = Path(template_rel_path).resolve()

            if not tpl_path.is_file():
                raise ValueError(f"Template image file not found: {tpl_path}")

            tpl_img = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
            if tpl_img is None:
                raise ValueError(f"Failed to read template image from: {tpl_path}")

            state._cached_template = tpl_img
            state._cached_template_path = template_rel_path

        tpl = state._cached_template
        th, tw = tpl.shape[:2]
        fh, fw = frame_bgr.shape[:2]

        if fh < th or fw < tw:
            return {
                "raw_on": False,
                "score": 0.0,
                "metrics": {
                    "max_val": 0.0,
                    "threshold": threshold,
                    "error": "frame_smaller_than_template",
                },
            }

        res = cv2.matchTemplate(frame_bgr, tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        max_val_f = float(max_val)
        is_on = max_val_f >= threshold
        score = max(0.0, min(1.0, max_val_f))

        metrics = {
            "max_val": round(max_val_f, 4),
            "threshold": threshold,
            "match_loc": [int(max_loc[0]), int(max_loc[1])],
        }
        return {"raw_on": is_on, "score": score, "metrics": metrics}

    def _eval_change(self, state: RegionState, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """Difference pixel ratio compared to previous frame >= diff_ratio."""
        rule = state.region.rule
        sens = _clamp_sens(rule.get("sensitivity", self.base_sensitivity))
        diff_ratio_thresh = _easier_lower(rule.get("diff_ratio", 0.08), sens)
        diff_threshold = int(rule.get("diff_threshold", 25))

        # Small scale for fast diff calculation
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        # Downscale if larger than 128x128 to keep O(small)
        if max(h, w) > 128:
            scale = 128.0 / max(h, w)
            gray_small = cv2.resize(
                gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
            )
        else:
            gray_small = gray

        if state.prev_frame_gray is None:
            state.prev_frame_gray = gray_small
            return {
                "raw_on": False,
                "score": 0.0,
                "metrics": {"diff_ratio": 0.0, "reason": "first_frame"},
            }

        # Handle size mismatch if resized
        if state.prev_frame_gray.shape != gray_small.shape:
            state.prev_frame_gray = gray_small
            return {
                "raw_on": False,
                "score": 0.0,
                "metrics": {"diff_ratio": 0.0, "reason": "size_changed"},
            }

        diff = cv2.absdiff(gray_small, state.prev_frame_gray)
        state.prev_frame_gray = gray_small

        _, thresh = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)
        total_px = thresh.shape[0] * thresh.shape[1]
        changed_px = int(cv2.countNonZero(thresh))
        ratio = float(changed_px / total_px) if total_px > 0 else 0.0

        is_on = ratio >= diff_ratio_thresh
        score = min(1.0, ratio / diff_ratio_thresh) if diff_ratio_thresh > 0 else 1.0

        metrics = {
            "diff_ratio": round(ratio, 4),
            "diff_threshold": diff_threshold,
            "diff_ratio_thresh": diff_ratio_thresh,
        }
        return {"raw_on": is_on, "score": score, "metrics": metrics}
