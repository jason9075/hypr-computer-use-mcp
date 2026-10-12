"""MCP server exposing computer-use tools for a Hyprland session.

By default every tool acts on the *realm*: a nested Hyprland in a window on its own workspace that
gives the agent its own seat, cursor and focus. Set HYPR_CU_TARGET=host to drive the user's own
desktop.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations

from . import hypr, realm, vpointer
from .geometry import Viewport, interpolate, to_global, to_local, viewport_from_monitor
from .keys import wtype_args
from .target import Target, TargetError, host_target, runtime_dir

log = logging.getLogger("hypr_computer_use")

MAX_EDGE = int(os.environ.get("HYPR_CU_MAX_EDGE", "1280"))
MODE = os.environ.get("HYPR_CU_TARGET", "realm")
SCROLL_UNIT = 15  # wl_pointer axis value of one wheel notch
SETTLE_S = 0.05  # let the compositor deliver motion before a click lands

Button = Literal["left", "right", "middle"]

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ACTION = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

_REALM_GUIDE = (
  "You operate inside a private 'realm': a separate Hyprland desktop on the user's workspace "
  f"{realm.REALM_WS}, with its own cursor and keyboard focus, so you never disturb the user. "
  "Call `start_realm` first if it is not running, then open apps with `open_url` or `launch`. "
  "The user can watch or take over by switching to that workspace; call `stop_realm` when the "
  "task is done. While hidden the realm renders at about 15 FPS, so allow a moment after acting "
  "before judging a screenshot."
)
_HOST_GUIDE = (
  "You control the user's LIVE desktop: clicks and keystrokes go to whatever they are using."
)

mcp = FastMCP(
  "hypr-computer-use",
  instructions=(
    (_REALM_GUIDE if MODE == "realm" else _HOST_GUIDE)
    + " Call `screenshot` before acting: every x/y argument is in pixels of the most recent "
    "screenshot image. Take a new screenshot after acting to verify the result."
  ),
)

# Coordinates refer to the last screenshot the model saw *of that session*, so the mapping is
# kept per target signature.
_viewports: dict[str, Viewport] = {}


def _host() -> Target:
  state = realm.read_state(runtime_dir(os.environ))
  return host_target(os.environ, frozenset({state.signature}) if state else frozenset())


def _target() -> Target:
  host = _host()
  if MODE == "host":
    return host
  state = realm.read_state(host.runtime_dir)
  why = realm.problem(host, state)
  if why is not None:
    raise TargetError(f"{why}; call start_realm first")
  assert state is not None
  realm.mark_activity(host.runtime_dir)
  return realm.as_target(state, host.runtime_dir)


def _monitor(target: Target, name: str | None) -> dict[str, Any]:
  mons = hypr.monitors(target)
  pick = (m for m in mons if m["name"] == name) if name else (m for m in mons if m["focused"])
  mon = next(pick, None)
  if mon is None:
    raise ValueError(f"monitor {name!r} not found; available: {[m['name'] for m in mons]}")
  return mon


def _viewport(target: Target) -> Viewport:
  cached = _viewports.get(target.signature)
  return cached or viewport_from_monitor(_monitor(target, None), MAX_EDGE)


def _move(target: Target, x: int, y: int) -> None:
  hypr.move_cursor(target, *to_global(_viewport(target), x, y))
  time.sleep(SETTLE_S)


# Prompts that would otherwise cost the agent a screenshot-and-click on every launch.
FIREFOX_PREFS = {
  "browser.sessionstore.resume_from_crash": False,  # realm stops kill Firefox
  "browser.translations.automaticallyPopup": False,
  "browser.aboutwelcome.enabled": False,
  "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
  "layout.frame_rate": -1,  # undo an earlier cap; video ignores it and hidden realms run at 15
}


def _firefox_profile() -> Path:
  """The realm's persistent Firefox profile, with agent-friendly prefs (re)applied."""
  data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
  profile = Path(data, "hypr-cu", "firefox-profile")
  profile.mkdir(parents=True, exist_ok=True)
  lines = [f"user_pref({json.dumps(k)}, {json.dumps(v)});" for k, v in FIREFOX_PREFS.items()]
  (profile / "user.js").write_text(
    "// Managed by hypr-computer-use-mcp.\n" + "\n".join(lines) + "\n"
  )
  return profile


@mcp.tool(annotations=ACTION)
def start_realm() -> str:
  """Start the agent realm (idempotent; also repairs a broken one)."""
  if MODE == "host":
    return "HYPR_CU_TARGET=host: acting on the user's desktop, no realm needed"
  target = realm.up(_host())
  _viewports.pop(target.signature, None)
  return f"realm running on workspace {realm.REALM_WS} ({target.wayland_display})"


@mcp.tool(annotations=ACTION)
def stop_realm() -> str:
  """Stop the realm and everything running inside it."""
  realm.down(_host())
  _viewports.clear()
  return "realm stopped"


@mcp.tool(annotations=ACTION)
def open_url(url: str) -> str:
  """Open a URL in the realm's Firefox (persistent profile, so logins survive restarts)."""
  target = _target()
  firefox = [c for c in hypr.clients(target) if c["class"] == "firefox"]
  if firefox:
    hypr.dispatch(target, "focuswindow", f"address:{firefox[0]['address']}")
    hypr.wtype(target, *wtype_args("ctrl+t"))
    time.sleep(0.3)
    hypr.wtype(target, "--", url)
    hypr.wtype(target, *wtype_args("Return"))
    return f"opened {url} in a new tab"
  profile = _firefox_profile()
  # --no-remote: otherwise Firefox hands the URL to the user's own instance on the host.
  cmd = shlex.join(["firefox", "--no-remote", "--profile", str(profile), url])
  hypr.dispatch(target, "exec", cmd)
  return f"launching Firefox with {url}; take a screenshot in a few seconds"


@mcp.tool(annotations=ACTION)
def launch(command: str) -> str:
  """Launch a program in the current session, e.g. "kitty" or "thunar"."""
  hypr.dispatch(_target(), "exec", command)
  return f"launched: {command}"


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def screenshot(monitor: str | None = None) -> list[Any]:
  """Capture a monitor (default: focused) and make it the coordinate space for later calls."""
  target = _target()
  vp = viewport_from_monitor(_monitor(target, monitor), MAX_EDGE)
  png = hypr.capture(target, vp)
  _viewports[target.signature] = vp
  w, h = vp.image_size
  return [Image(data=png, format="png"), f"{target.kind} monitor={vp.monitor} size={w}x{h}"]


@mcp.tool(annotations=READ_ONLY)
def list_monitors() -> list[dict[str, Any]]:
  """List monitors with name, focus state and active workspace."""
  return [
    {
      "name": m["name"],
      "focused": m["focused"],
      "active_workspace": m["activeWorkspace"]["name"],
      "description": m["description"],
    }
    for m in hypr.monitors(_target())
  ]


@mcp.tool(annotations=READ_ONLY)
def list_windows() -> list[dict[str, Any]]:
  """List mapped windows; `bbox` is in current screenshot coordinates when on that monitor."""
  target = _target()
  vp = _viewport(target)
  mons = {m["id"]: m["name"] for m in hypr.monitors(target)}
  result = []
  for c in hypr.clients(target):
    if not c["mapped"] or c["hidden"]:
      continue
    (x, y), (w, h) = c["at"], c["size"]
    on_screen = mons.get(c["monitor"]) == vp.monitor
    result.append(
      {
        "address": c["address"],
        "class": c["class"],
        "title": c["title"],
        "workspace": c["workspace"]["name"],
        "floating": c["floating"],
        "focused": c["focusHistoryID"] == 0,
        "bbox": [*to_local(vp, x, y), *to_local(vp, x + w, y + h)] if on_screen else None,
      }
    )
  return result


@mcp.tool(annotations=ACTION)
def focus_window(address: str) -> str:
  """Focus a window by the `address` returned from list_windows."""
  hypr.dispatch(_target(), "focuswindow", f"address:{address}")
  return f"focused {address}"


@mcp.tool(annotations=READ_ONLY)
def cursor_position() -> dict[str, int]:
  """Current cursor position in screenshot coordinates."""
  target = _target()
  x, y = to_local(_viewport(target), *hypr.cursor_pos(target))
  return {"x": x, "y": y}


@mcp.tool(annotations=ACTION)
def mouse_move(x: int, y: int) -> str:
  """Move the cursor to (x, y)."""
  _move(_target(), x, y)
  return f"moved to ({x}, {y})"


@mcp.tool(annotations=ACTION)
def click(x: int, y: int, button: Button = "left", count: int = 1) -> str:
  """Click at (x, y); count=2 for a double click."""
  if not 1 <= count <= 3:
    raise ValueError("count must be 1..3")
  target = _target()
  _move(target, x, y)
  for _ in range(count):
    hypr.click(target, button)
  return f"{button} x{count} at ({x}, {y})"


@mcp.tool(annotations=ACTION)
def scroll(x: int, y: int, down: int = 0, right: int = 0) -> str:
  """Scroll at (x, y) by wheel notches; negative values scroll up / left."""
  target = _target()
  _move(target, x, y)
  hypr.scroll(target, down * SCROLL_UNIT, right * SCROLL_UNIT)
  return f"scrolled down={down} right={right} at ({x}, {y})"


@mcp.tool(annotations=ACTION)
def drag(x1: int, y1: int, x2: int, y2: int, button: Button = "left", steps: int = 20) -> str:
  """Press at (x1, y1), move to (x2, y2), release."""
  target = _target()
  vp = _viewport(target)
  start, end = to_global(vp, x1, y1), to_global(vp, x2, y2)
  vpointer.drag(
    target,
    [start, *interpolate(start, end, steps)],
    button,
    move_to=lambda gx, gy: hypr.move_cursor(target, gx, gy),
    cursor_pos=lambda: hypr.cursor_pos(target),
  )
  return f"dragged ({x1}, {y1}) -> ({x2}, {y2})"


@mcp.tool(annotations=ACTION)
def type_text(text: str) -> str:
  """Type literal text into the focused window."""
  hypr.wtype(_target(), "--", text)
  return f"typed {len(text)} chars"


@mcp.tool(annotations=ACTION)
def key(combo: str) -> str:
  """Press a key combo, e.g. "Return", "ctrl+c", "ctrl+shift+t", "F5"."""
  hypr.wtype(_target(), *wtype_args(combo))
  return f"pressed {combo}"


def _realm_cli(action: str) -> int:
  host = _host()
  if action == "up":
    print(f"realm up: {realm.up(host).wayland_display}")
  elif action == "down":
    realm.down(host)
    print("realm down")
  else:
    why = realm.problem(host, realm.read_state(host.runtime_dir))
    print("realm healthy" if why is None else f"realm unavailable: {why}")
    return 0 if why is None else 1
  return 0


def main() -> None:
  """Entry point: serve MCP over stdio, or manage the realm (`realm up|down|status`).

  Logs go to stderr since stdout carries the protocol.
  """
  logging.basicConfig(level=os.environ.get("HYPR_CU_LOG", "WARNING"))
  parser = argparse.ArgumentParser(prog="hypr-computer-use-mcp")
  sub = parser.add_subparsers(dest="cmd")
  realm_cmd = sub.add_parser("realm", help="manage the agent realm")
  realm_cmd.add_argument("action", choices=["up", "down", "status"])
  args = parser.parse_args()
  if args.cmd == "realm":
    sys.exit(_realm_cli(args.action))
  mcp.run()


if __name__ == "__main__":
  main()
