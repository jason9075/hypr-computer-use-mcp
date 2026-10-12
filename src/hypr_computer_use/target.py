"""Which Hyprland session a tool acts on, and the environment needed to reach it.

MCP hosts may spawn servers with a stripped environment (no HYPRLAND_INSTANCE_SIGNATURE or
WAYLAND_DISPLAY), so sessions are also discoverable from $XDG_RUNTIME_DIR/hypr/*/hyprland.lock,
whose lines are the compositor PID and its Wayland socket name.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TargetKind = Literal["host", "realm"]


class TargetError(RuntimeError):
  """No usable Hyprland session was found."""


@dataclass(frozen=True, slots=True)
class Instance:
  """A live Hyprland instance as recorded in its lock file."""

  signature: str
  wayland_display: str
  pid: int


@dataclass(frozen=True, slots=True)
class Target:
  """A Hyprland session plus what child tools need in their environment to reach it."""

  kind: TargetKind
  signature: str
  wayland_display: str
  runtime_dir: str

  def env(self, base: Mapping[str, str]) -> dict[str, str]:
    """`base` with this session's variables overlaid."""
    return {
      **base,
      "XDG_RUNTIME_DIR": self.runtime_dir,
      "WAYLAND_DISPLAY": self.wayland_display,
      "HYPRLAND_INSTANCE_SIGNATURE": self.signature,
    }

  @property
  def socket_path(self) -> str:
    """Absolute Wayland socket path, usable regardless of this process's env."""
    return str(Path(self.runtime_dir, self.wayland_display))


def runtime_dir(environ: Mapping[str, str]) -> str:
  """$XDG_RUNTIME_DIR, falling back to systemd-logind's standard per-user path."""
  return environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def pid_alive(pid: int) -> bool:
  """Whether `pid` is running; an exited-but-unreaped zombie counts as dead."""
  try:
    stat = Path("/proc", str(pid), "stat").read_text()
  except OSError:
    return False
  # The state field follows the parenthesised command name, which may itself contain spaces.
  return pid > 0 and stat[stat.rindex(")") + 2] != "Z"


def live_instances(runtime: str) -> list[Instance]:
  """Running Hyprland instances, newest first."""
  locks = sorted(
    Path(runtime, "hypr").glob("*/hyprland.lock"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
  )
  found = []
  for lock in locks:
    fields = lock.read_text().split()
    if len(fields) >= 2 and fields[0].isdigit() and pid_alive(int(fields[0])):
      found.append(Instance(lock.parent.name, fields[1], int(fields[0])))
  return found


def host_target(environ: Mapping[str, str], exclude: frozenset[str] = frozenset()) -> Target:
  """The user's own session: from the env if present, else the newest live instance.

  `exclude` holds signatures that must never be treated as the host (the realm, which is itself
  a newer Hyprland instance).

  Raises:
    TargetError: if no candidate instance is running.
  """
  runtime = runtime_dir(environ)
  sig, display = environ.get("HYPRLAND_INSTANCE_SIGNATURE"), environ.get("WAYLAND_DISPLAY")
  if sig and display and sig not in exclude:
    return Target("host", sig, display, runtime)
  for inst in live_instances(runtime):
    if inst.signature not in exclude:
      return Target("host", inst.signature, inst.wayland_display, runtime)
  raise TargetError(f"no running Hyprland instance found under {runtime}/hypr")
