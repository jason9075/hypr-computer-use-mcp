"""Recover the Hyprland/Wayland session environment when the MCP host strips it.

Some MCP clients spawn servers with a minimal env (no HYPRLAND_INSTANCE_SIGNATURE or
WAYLAND_DISPLAY), which leaves hyprctl, grim, wtype and wlrctl unable to reach the session.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

log = logging.getLogger(__name__)

REQUIRED = ("XDG_RUNTIME_DIR", "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY")


def _alive(pid: str) -> bool:
  return pid.isdigit() and Path("/proc", pid).exists()


def discover(environ: Mapping[str, str]) -> dict[str, str]:
  """Return the missing session variables, taken from the newest live Hyprland instance.

  Each instance dir under $XDG_RUNTIME_DIR/hypr/<signature>/ holds a hyprland.lock whose
  lines are the compositor PID and its Wayland socket name.
  """
  if all(environ.get(k) for k in REQUIRED):
    return {}

  # systemd-logind's standard per-user runtime dir is the only sane fallback.
  runtime = environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
  locks = sorted(
    Path(runtime, "hypr").glob("*/hyprland.lock"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
  )
  for lock in locks:
    lines = lock.read_text().split()
    if len(lines) >= 2 and _alive(lines[0]):
      found = {
        "XDG_RUNTIME_DIR": runtime,
        "HYPRLAND_INSTANCE_SIGNATURE": lock.parent.name,
        "WAYLAND_DISPLAY": lines[1],
      }
      return {k: v for k, v in found.items() if not environ.get(k)}

  log.warning("no running Hyprland instance found under %s/hypr", runtime)
  return {}
