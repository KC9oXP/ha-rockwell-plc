"""Tag list parsing. Deliberately free of Home Assistant imports so it can be unit tested."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

READ_PLATFORMS = {"sensor", "binary_sensor"}
WRITE_PLATFORMS = {"switch", "number", "button"}
ALL_PLATFORMS = READ_PLATFORMS | WRITE_PLATFORMS

# When writes are disabled, write platforms fall back to a read-only equivalent.
# Buttons have no read equivalent and are dropped.
READ_ONLY_FALLBACK = {"switch": "binary_sensor", "number": "sensor", "button": None}

_KNOWN_KEYS = {
    "tag", "name", "platform", "unit", "scale", "offset", "precision",
    "device_class", "state_class", "icon", "min", "max", "step", "mode",
    "invert", "press_value", "release_value", "pulse_ms",
}


class TagConfigError(ValueError):
    """Raised when the tag YAML is invalid."""


@dataclass(frozen=True)
class TagConfig:
    """One configured tag/address."""

    tag: str
    name: str
    platform: str
    unit: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    precision: int | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None
    min: float = 0.0
    max: float = 100.0
    step: float = 1.0
    mode: str = "box"
    invert: bool = False
    press_value: Any = True
    release_value: Any = False
    pulse_ms: int = 500

    @property
    def key(self) -> str:
        """Stable identity used for unique_id. Uses the configured platform."""
        return f"{self.platform}_{self.tag}"

    def effective_platform(self, allow_writes: bool) -> str | None:
        """Platform to actually create, given the write setting."""
        if allow_writes or self.platform in READ_PLATFORMS:
            return self.platform
        return READ_ONLY_FALLBACK[self.platform]

    def to_ha(self, raw: Any) -> Any:
        """Raw PLC value -> Home Assistant value (scale/offset numerics only)."""
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return raw
        if self.scale == 1.0 and self.offset == 0.0:
            return raw
        return raw * self.scale + self.offset

    def to_raw(self, value: float) -> float:
        """Home Assistant value -> raw PLC value."""
        return (value - self.offset) / self.scale


def _num(item: dict, key: str, default: float, idx: int) -> float:
    val = item.get(key, default)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TagConfigError(f"entry {idx} ({item.get('tag')}): '{key}' must be a number")
    return float(val)


def parse_tags(text: str | None) -> list[TagConfig]:
    """Parse the YAML tag list. Empty text -> empty list."""
    if not text or not text.strip():
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise TagConfigError(f"YAML syntax error: {err}") from err
    if data is None:
        return []
    if not isinstance(data, list):
        raise TagConfigError("tag list must be a YAML list (each entry starts with '- tag:')")

    result: list[TagConfig] = []
    seen: set[str] = set()
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise TagConfigError(f"entry {idx} must be a mapping with at least 'tag'")
        unknown = set(item) - _KNOWN_KEYS
        if unknown:
            raise TagConfigError(f"entry {idx}: unknown key(s) {sorted(unknown)}")

        tag = item.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            raise TagConfigError(f"entry {idx}: 'tag' is required and must be text")
        tag = tag.strip()

        platform = str(item.get("platform", "sensor")).strip().lower()
        if platform not in ALL_PLATFORMS:
            raise TagConfigError(
                f"entry {idx} ({tag}): platform must be one of {sorted(ALL_PLATFORMS)}"
            )

        scale = _num(item, "scale", 1.0, idx)
        if scale == 0:
            raise TagConfigError(f"entry {idx} ({tag}): 'scale' cannot be 0")

        precision = item.get("precision")
        if precision is not None and (isinstance(precision, bool) or not isinstance(precision, int)):
            raise TagConfigError(f"entry {idx} ({tag}): 'precision' must be a whole number")

        mode = str(item.get("mode", "box")).lower()
        if mode not in ("box", "slider", "auto"):
            raise TagConfigError(f"entry {idx} ({tag}): 'mode' must be box, slider or auto")

        pulse_ms = item.get("pulse_ms", 500)
        if isinstance(pulse_ms, bool) or not isinstance(pulse_ms, int) or not 0 <= pulse_ms <= 60000:
            raise TagConfigError(f"entry {idx} ({tag}): 'pulse_ms' must be 0-60000")

        cfg = TagConfig(
            tag=tag,
            name=str(item.get("name") or tag),
            platform=platform,
            unit=str(item["unit"]) if item.get("unit") is not None else None,
            scale=scale,
            offset=_num(item, "offset", 0.0, idx),
            precision=precision,
            device_class=item.get("device_class"),
            state_class=item.get("state_class"),
            icon=item.get("icon"),
            min=_num(item, "min", 0.0, idx),
            max=_num(item, "max", 100.0, idx),
            step=_num(item, "step", 1.0, idx),
            mode=mode,
            invert=bool(item.get("invert", False)),
            press_value=item.get("press_value", True),
            release_value=item.get("release_value", False),
            pulse_ms=pulse_ms,
        )
        if cfg.min > cfg.max:
            raise TagConfigError(f"entry {idx} ({tag}): 'min' is greater than 'max'")
        if cfg.key in seen:
            raise TagConfigError(f"entry {idx}: '{tag}' is listed twice as {platform}")
        seen.add(cfg.key)
        result.append(cfg)
    return result


def coerce_for_write(value: Any, last_raw: Any) -> Any:
    """Match the type of the value last read from the PLC so the driver packs it correctly."""
    if isinstance(last_raw, bool):
        return bool(value)
    if isinstance(last_raw, int):
        return int(round(float(value)))
    if isinstance(last_raw, float):
        return float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value
