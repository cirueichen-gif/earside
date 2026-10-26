"""Preset data models and loading/validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class Region:
    name: str
    rect: Tuple[float, float, float, float]
    interval_ms: int
    rule: Dict[str, Any]


@dataclass
class Preset:
    id: str
    name: str
    match: Dict[str, Any]
    reference_aspect: float
    regions: List[Region] = field(default_factory=list)
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    vision: Dict[str, Any] = field(default_factory=dict)
    base_dir: Optional[Path] = None
    game_type: str = "generic"
    enabled: bool = True
    sensitivity: float = 1.0


def load_preset(path: Union[str, Path]) -> Preset:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Preset file not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON in preset '{p}': {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Preset root must be a JSON object, got {type(data).__name__}")

    # Validate required root fields
    for req in ("id", "name", "match", "reference_aspect", "regions"):
        if req not in data:
            raise ValueError(f"Missing required field in preset: '{req}'")

    if not isinstance(data["id"], str) or not data["id"].strip():
        raise ValueError("Field 'id' must be a non-empty string")

    if not isinstance(data["name"], str) or not data["name"].strip():
        raise ValueError("Field 'name' must be a non-empty string")

    if not isinstance(data["match"], dict):
        raise ValueError("Field 'match' must be an object")

    try:
        ref_aspect = float(data["reference_aspect"])
        if ref_aspect <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Field 'reference_aspect' must be a positive number")

    raw_regions = data.get("regions")
    if not isinstance(raw_regions, list):
        raise ValueError("Field 'regions' must be a list")

    parsed_regions: List[Region] = []
    seen_names: set[str] = set()

    for idx, r_data in enumerate(raw_regions):
        if not isinstance(r_data, dict):
            raise ValueError(f"regions[{idx}] must be an object")

        for r_req in ("name", "rect", "interval_ms", "rule"):
            if r_req not in r_data:
                raise ValueError(f"regions[{idx}] missing required field '{r_req}'")

        name = r_data["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"regions[{idx}].name must be a non-empty string")
        if name in seen_names:
            raise ValueError(f"Duplicate region name '{name}' at index {idx}")
        seen_names.add(name)

        rect = r_data["rect"]
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise ValueError(
                f"regions[{idx}] ('{name}').rect must be a list/tuple of 4 numbers [x, y, w, h]"
            )

        try:
            rect_floats = tuple(float(v) for v in rect)
        except (TypeError, ValueError):
            raise ValueError(
                f"regions[{idx}] ('{name}').rect elements must be valid numbers"
            )

        for elem_idx, val in enumerate(rect_floats):
            if val < 0.0 or val > 1.0:
                raise ValueError(
                    f"regions[{idx}] ('{name}').rect[{elem_idx}]={val} is out of bounds [0, 1]"
                )

        interval = r_data["interval_ms"]
        if not isinstance(interval, (int, float)) or interval <= 0:
            raise ValueError(
                f"regions[{idx}] ('{name}').interval_ms must be a positive number, got {interval}"
            )
        interval_ms = int(interval)

        rule = r_data["rule"]
        if not isinstance(rule, dict):
            raise ValueError(f"regions[{idx}] ('{name}').rule must be an object")
        if "type" not in rule:
            raise ValueError(f"regions[{idx}] ('{name}').rule missing required field 'type'")

        parsed_regions.append(
            Region(
                name=name,
                rect=(rect_floats[0], rect_floats[1], rect_floats[2], rect_floats[3]),
                interval_ms=interval_ms,
                rule=rule,
            )
        )

    triggers = data.get("triggers", [])
    if not isinstance(triggers, list):
        raise ValueError("Field 'triggers' must be a list")

    vision = data.get("vision", {})
    if not isinstance(vision, dict):
        raise ValueError("Field 'vision' must be an object")

    game_type = data.get("game_type", "generic")
    if not isinstance(game_type, str):
        raise ValueError("Field 'game_type' must be a string")

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("Field 'enabled' must be a boolean")

    sensitivity = data.get("sensitivity", 1.0)
    try:
        sensitivity = float(sensitivity)
    except (TypeError, ValueError):
        raise ValueError("Field 'sensitivity' must be a number")
    if not (0.25 <= sensitivity <= 4.0):
        raise ValueError("Field 'sensitivity' must be between 0.25 and 4.0")

    return Preset(
        id=data["id"],
        name=data["name"],
        match=data["match"],
        reference_aspect=ref_aspect,
        regions=parsed_regions,
        triggers=triggers,
        vision=vision,
        base_dir=p.parent.resolve(),
        game_type=game_type,
        enabled=enabled,
        sensitivity=sensitivity,
    )
