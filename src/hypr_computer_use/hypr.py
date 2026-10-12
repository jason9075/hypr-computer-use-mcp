"""Side-effecting wrappers around hyprctl, grim, wtype and wlrctl, addressed to a Target."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .geometry import Viewport
from .target import Target

log = logging.getLogger(__name__)

TIMEOUT_S = 10.0


class CommandError(RuntimeError):
  """An external tool failed or is missing."""


def run(*args: str, target: Target) -> bytes:
  """Run a command against `target`'s session; raise CommandError with its output on failure."""
  log.debug("exec %s on %s", args, target.kind)
  try:
    proc = subprocess.run(
      args, capture_output=True, timeout=TIMEOUT_S, check=False, env=target.env(os.environ)
    )
  except FileNotFoundError as exc:
    raise CommandError(f"{args[0]} not found on PATH") from exc
  except subprocess.TimeoutExpired as exc:
    raise CommandError(f"{args[0]} timed out after {TIMEOUT_S}s") from exc
  if proc.returncode != 0:
    # hyprctl reports errors on stdout, so fall back to it when stderr is empty.
    detail = (proc.stderr or proc.stdout).decode(errors="replace").strip()
    raise CommandError(f"{' '.join(args)} exited {proc.returncode}: {detail}")
  return proc.stdout


def hyprctl_json(target: Target, *args: str) -> Any:
  """Query hyprctl with JSON output."""
  out = run("hyprctl", "-j", *args, target=target)
  try:
    return json.loads(out)
  except json.JSONDecodeError as exc:
    # hyprctl can exit 0 with a plain-text error (e.g. no instance reachable).
    text = out.decode(errors="replace").strip()
    raise CommandError(f"hyprctl -j {' '.join(args)}: {text}") from exc


def _expect_ok(args: tuple[str, ...], target: Target) -> None:
  # hyprctl exits 0 even when a dispatcher/keyword fails, so check the reply text.
  reply = run("hyprctl", *args, target=target).decode().strip()
  if not all(line == "ok" for line in reply.splitlines() if line):
    raise CommandError(f"hyprctl {' '.join(args)}: {reply}")


def dispatch(target: Target, *args: str) -> None:
  """Run a Hyprland dispatcher."""
  _expect_ok(("dispatch", *args), target)


def keyword(target: Target, *args: str) -> None:
  """Set a Hyprland config keyword at runtime."""
  _expect_ok(("keyword", *args), target)


def batch(target: Target, *commands: str) -> None:
  """Run several hyprctl commands atomically (no input is processed in between)."""
  _expect_ok(("--batch", "; ".join(commands)), target)


def monitors(target: Target) -> list[dict[str, Any]]:
  return hyprctl_json(target, "monitors")


def clients(target: Target) -> list[dict[str, Any]]:
  return hyprctl_json(target, "clients")


def active_window(target: Target) -> dict[str, Any]:
  return hyprctl_json(target, "activewindow")


def cursor_pos(target: Target) -> tuple[int, int]:
  pos = hyprctl_json(target, "cursorpos")
  return pos["x"], pos["y"]


def move_cursor(target: Target, gx: int, gy: int) -> None:
  """Warp the cursor to global logical coordinates."""
  dispatch(target, "movecursor", str(gx), str(gy))


def capture(target: Target, vp: Viewport) -> bytes:
  """Screenshot a monitor as PNG at the viewport's scale."""
  return run("grim", "-o", vp.monitor, "-s", f"{vp.factor:.6f}", "-t", "png", "-", target=target)


def click(target: Target, button: str) -> None:
  run("wlrctl", "pointer", "click", button, target=target)


def scroll(target: Target, dy: int, dx: int) -> None:
  run("wlrctl", "pointer", "scroll", str(dy), str(dx), target=target)


@contextmanager
def ime_suspended(target: Target) -> Iterator[None]:
  """Temporarily deactivate the host's fcitx5 so virtual keystrokes reach the app verbatim.

  An active input method intercepts wtype's events (e.g. Zhuyin turns "abc" into bopomofo
  composition). A realm runs no input method, so only the host needs this.
  """
  # fcitx5-remote prints 2 when the input method is active.
  if (
    target.kind != "host"
    or shutil.which("fcitx5-remote") is None
    or run("fcitx5-remote", target=target).strip() != b"2"
  ):
    yield
    return
  run("fcitx5-remote", "-c", target=target)
  try:
    yield
  finally:
    run("fcitx5-remote", "-o", target=target)


def wtype(target: Target, *args: str) -> None:
  with ime_suspended(target):
    run("wtype", *args, target=target)
