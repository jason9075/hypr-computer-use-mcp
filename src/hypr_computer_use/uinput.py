"""Press-and-hold mouse buttons via /dev/uinput.

The Wayland virtual-pointer path (wlrctl) only offers atomic clicks, so drags need a real
evdev device. This requires write access to /dev/uinput (NixOS: hardware.uinput.enable plus
the "uinput" group).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Any

# libinput only picks up a freshly created device after a short delay.
DEVICE_SETTLE_S = 0.3
STEP_DELAY_S = 0.01


class UinputUnavailable(RuntimeError):
  """/dev/uinput cannot be opened."""


@contextmanager
def _device() -> Any:
  try:
    from evdev import UInput, UInputError
    from evdev import ecodes as e
  except ImportError as exc:
    raise UinputUnavailable("python evdev module is not installed") from exc

  # REL axes are required for libinput to classify the device as a pointer.
  caps = {
    e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
    e.EV_REL: [e.REL_X, e.REL_Y],
  }
  try:
    ui = UInput(caps, name="hypr-computer-use")
  except (OSError, UInputError) as exc:
    raise UinputUnavailable(
      f"cannot open /dev/uinput ({exc}); enable hardware.uinput and join the uinput group"
    ) from exc
  try:
    time.sleep(DEVICE_SETTLE_S)
    yield ui, e
  finally:
    ui.close()


def drag(
  path: Iterable[tuple[int, int]],
  move: Callable[[int, int], None],
  button: str = "left",
) -> None:
  """Hold `button` while moving through `path` (global coords) using `move` to warp the cursor."""
  points = list(path)
  if len(points) < 2:
    raise ValueError("drag path needs at least two points")

  with _device() as (ui, e):
    btn = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}[button]
    move(*points[0])
    ui.write(e.EV_KEY, btn, 1)
    ui.syn()
    try:
      for point in points[1:]:
        time.sleep(STEP_DELAY_S)
        move(*point)
    finally:
      # Always release, or the button stays logically held for the whole session.
      ui.write(e.EV_KEY, btn, 0)
      ui.syn()
