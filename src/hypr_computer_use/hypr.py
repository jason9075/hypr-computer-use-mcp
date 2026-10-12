"""Side-effecting wrappers around hyprctl, grim, wtype and wlrctl."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .geometry import Viewport

log = logging.getLogger(__name__)

TIMEOUT_S = 10.0


class CommandError(RuntimeError):
  """An external tool failed or is missing."""


def run(*args: str) -> bytes:
  """Run a command and return stdout, raising CommandError with stderr on failure."""
  log.debug("exec %s", args)
  try:
    proc = subprocess.run(args, capture_output=True, timeout=TIMEOUT_S, check=False)
  except FileNotFoundError as exc:
    raise CommandError(f"{args[0]} not found on PATH") from exc
  except subprocess.TimeoutExpired as exc:
    raise CommandError(f"{args[0]} timed out after {TIMEOUT_S}s") from exc
  if proc.returncode != 0:
    # hyprctl reports errors on stdout, so fall back to it when stderr is empty.
    detail = (proc.stderr or proc.stdout).decode(errors="replace").strip()
    raise CommandError(f"{' '.join(args)} exited {proc.returncode}: {detail}")
  return proc.stdout


def hyprctl_json(*args: str) -> Any:
  """Query hyprctl with JSON output."""
  out = run("hyprctl", "-j", *args)
  try:
    return json.loads(out)
  except json.JSONDecodeError as exc:
    # hyprctl can exit 0 with a plain-text error (e.g. no instance reachable).
    text = out.decode(errors="replace").strip()
    raise CommandError(f"hyprctl -j {' '.join(args)}: {text}") from exc


def dispatch(*args: str) -> None:
  """Run a Hyprland dispatcher; hyprctl exits 0 even on failure, so check the reply text."""
  reply = run("hyprctl", "dispatch", *args).decode().strip()
  if reply != "ok":
    raise CommandError(f"hyprctl dispatch {' '.join(args)}: {reply}")


def monitors() -> list[dict[str, Any]]:
  return hyprctl_json("monitors")


def clients() -> list[dict[str, Any]]:
  return hyprctl_json("clients")


def cursor_pos() -> tuple[int, int]:
  pos = hyprctl_json("cursorpos")
  return pos["x"], pos["y"]


def move_cursor(gx: int, gy: int) -> None:
  """Warp the cursor to global logical coordinates."""
  dispatch("movecursor", str(gx), str(gy))


def capture(vp: Viewport) -> bytes:
  """Screenshot a monitor as PNG at the viewport's scale."""
  return run("grim", "-o", vp.monitor, "-s", f"{vp.factor:.6f}", "-t", "png", "-")


def click(button: str) -> None:
  run("wlrctl", "pointer", "click", button)


def scroll(dy: int, dx: int) -> None:
  run("wlrctl", "pointer", "scroll", str(dy), str(dx))


@contextmanager
def ime_suspended() -> Iterator[None]:
  """Temporarily deactivate fcitx5 so virtual-keyboard events reach the app verbatim.

  An active input method intercepts wtype's keystrokes (e.g. Zhuyin turns "abc" into
  bopomofo composition), breaking both typing and single-key shortcuts.
  """
  # fcitx5-remote prints 2 when the input method is active; absent fcitx means nothing to do.
  if shutil.which("fcitx5-remote") is None or run("fcitx5-remote").strip() != b"2":
    yield
    return
  run("fcitx5-remote", "-c")
  try:
    yield
  finally:
    run("fcitx5-remote", "-o")


def wtype(*args: str) -> None:
  with ime_suspended():
    run("wtype", *args)
