"""Pure transforms between screenshot pixels and Hyprland's global logical layout space."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Viewport:
  """One monitor as captured by a screenshot.

  `factor` is screenshot pixels per logical pixel; the origin is the monitor's position in
  Hyprland's global layout.
  """

  monitor: str
  origin_x: int
  origin_y: int
  logical_w: int
  logical_h: int
  factor: float

  @property
  def image_size(self) -> tuple[int, int]:
    """Size of the screenshot image in pixels."""
    return round(self.logical_w * self.factor), round(self.logical_h * self.factor)


def viewport_from_monitor(mon: dict[str, Any], max_edge: int) -> Viewport:
  """Build a viewport for a `hyprctl -j monitors` entry, downscaled so its long edge <= max_edge."""
  w, h = mon["width"], mon["height"]
  # Odd transforms are 90/270-degree rotations, which swap the logical axes.
  if mon["transform"] % 2 == 1:
    w, h = h, w
  lw, lh = round(w / mon["scale"]), round(h / mon["scale"])
  factor = min(1.0, max_edge / max(lw, lh))
  return Viewport(mon["name"], mon["x"], mon["y"], lw, lh, factor)


def to_global(vp: Viewport, x: int, y: int) -> tuple[int, int]:
  """Map screenshot coordinates to global logical coordinates.

  Raises:
    ValueError: if (x, y) lies outside the screenshot.
  """
  iw, ih = vp.image_size
  if not (0 <= x < iw and 0 <= y < ih):
    raise ValueError(f"({x}, {y}) is outside the {iw}x{ih} screenshot of {vp.monitor}")
  return vp.origin_x + round(x / vp.factor), vp.origin_y + round(y / vp.factor)


def to_local(vp: Viewport, gx: float, gy: float) -> tuple[int, int]:
  """Map global logical coordinates to screenshot coordinates (may fall outside the image)."""
  return round((gx - vp.origin_x) * vp.factor), round((gy - vp.origin_y) * vp.factor)


def interpolate(start: tuple[int, int], end: tuple[int, int], steps: int) -> list[tuple[int, int]]:
  """Evenly spaced points from start (exclusive) to end (inclusive)."""
  (x0, y0), (x1, y1) = start, end
  n = max(1, steps)
  return [(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)) for i in range(1, n + 1)]
