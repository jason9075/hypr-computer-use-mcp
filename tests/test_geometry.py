import pytest

from hypr_computer_use.geometry import (
  Viewport,
  interpolate,
  to_global,
  to_local,
  viewport_from_monitor,
)


def _mon(**overrides):
  base = {"name": "DP-1", "x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0}
  return {"transform": 0, **base, **overrides}


def test_downscales_to_max_edge():
  vp = viewport_from_monitor(_mon(), 1280)
  assert vp.image_size == (1280, 720)


def test_never_upscales():
  assert viewport_from_monitor(_mon(), 4000).factor == 1.0


def test_hidpi_uses_logical_size():
  vp = viewport_from_monitor(_mon(width=3840, height=2160, scale=2.0), 1920)
  assert (vp.logical_w, vp.logical_h, vp.factor) == (1920, 1080, 1.0)


def test_rotated_monitor_swaps_axes():
  vp = viewport_from_monitor(_mon(transform=1), 4000)
  assert (vp.logical_w, vp.logical_h) == (1080, 1920)


def test_round_trip_with_offset_monitor():
  vp = viewport_from_monitor(_mon(x=1920, y=-200), 1280)
  assert to_global(vp, 640, 360) == (1920 + 960, -200 + 540)
  assert to_local(vp, *to_global(vp, 640, 360)) == (640, 360)


@pytest.mark.parametrize("x,y", [(-1, 0), (0, -1), (1280, 0), (0, 720)])
def test_rejects_out_of_bounds(x, y):
  vp = Viewport("DP-1", 0, 0, 1920, 1080, 2 / 3)
  with pytest.raises(ValueError):
    to_global(vp, x, y)


def test_interpolate_ends_at_target():
  pts = interpolate((0, 0), (10, 20), 4)
  assert pts == [(2, 5), (5, 10), (8, 15), (10, 20)]
