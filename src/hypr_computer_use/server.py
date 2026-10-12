"""MCP server exposing computer-use tools for the current Hyprland session."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations

from . import hypr, session, uinput
from .geometry import Viewport, interpolate, to_global, to_local, viewport_from_monitor
from .keys import wtype_args

log = logging.getLogger("hypr_computer_use")

MAX_EDGE = int(os.environ.get("HYPR_CU_MAX_EDGE", "1280"))
SCROLL_UNIT = 15  # wl_pointer axis value of one wheel notch
SETTLE_S = 0.05  # let the compositor deliver motion before a click lands

Button = Literal["left", "right", "middle"]

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
ACTION = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

mcp = FastMCP(
  "hypr-computer-use",
  instructions=(
    "Controls the user's live Hyprland desktop. Call `screenshot` first: every x/y argument "
    "is in pixels of the most recent screenshot image. Take a new screenshot after acting "
    "to verify the result."
  ),
)

# Coordinates in every tool refer to the last screenshot the model saw, so that mapping is the
# one piece of state shared between calls.
_viewport: Viewport | None = None


def _monitor(name: str | None) -> dict[str, Any]:
  mons = hypr.monitors()
  pick = (m for m in mons if m["name"] == name) if name else (m for m in mons if m["focused"])
  mon = next(pick, None)
  if mon is None:
    raise ValueError(f"monitor {name!r} not found; available: {[m['name'] for m in mons]}")
  return mon


def _current_viewport() -> Viewport:
  return _viewport or viewport_from_monitor(_monitor(None), MAX_EDGE)


def _point(x: int, y: int) -> tuple[int, int]:
  return to_global(_current_viewport(), x, y)


def _move(x: int, y: int) -> tuple[int, int]:
  gx, gy = _point(x, y)
  hypr.move_cursor(gx, gy)
  time.sleep(SETTLE_S)
  return gx, gy


@mcp.tool(annotations=READ_ONLY, structured_output=False)
def screenshot(monitor: str | None = None) -> list[Any]:
  """Capture a monitor (default: focused) and make it the coordinate space for later calls."""
  global _viewport
  vp = viewport_from_monitor(_monitor(monitor), MAX_EDGE)
  png = hypr.capture(vp)
  _viewport = vp
  w, h = vp.image_size
  return [Image(data=png, format="png"), f"monitor={vp.monitor} size={w}x{h}"]


@mcp.tool(annotations=READ_ONLY)
def list_monitors() -> list[dict[str, Any]]:
  """List monitors with name, focus state and logical geometry."""
  return [
    {
      "name": m["name"],
      "focused": m["focused"],
      "active_workspace": m["activeWorkspace"]["name"],
      "description": m["description"],
    }
    for m in hypr.monitors()
  ]


@mcp.tool(annotations=READ_ONLY)
def list_windows() -> list[dict[str, Any]]:
  """List mapped windows; `bbox` is in current screenshot coordinates when on that monitor."""
  vp = _current_viewport()
  mons = {m["id"]: m["name"] for m in hypr.monitors()}
  result = []
  for c in hypr.clients():
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
  """Focus a window by the `address` returned from list_windows (switches workspace if needed)."""
  hypr.dispatch("focuswindow", f"address:{address}")
  return f"focused {address}"


@mcp.tool(annotations=READ_ONLY)
def cursor_position() -> dict[str, int]:
  """Current cursor position in screenshot coordinates."""
  return dict(zip(("x", "y"), to_local(_current_viewport(), *hypr.cursor_pos()), strict=True))


@mcp.tool(annotations=ACTION)
def mouse_move(x: int, y: int) -> str:
  """Move the cursor to (x, y)."""
  _move(x, y)
  return f"moved to ({x}, {y})"


@mcp.tool(annotations=ACTION)
def click(x: int, y: int, button: Button = "left", count: int = 1) -> str:
  """Click at (x, y); count=2 for a double click."""
  if not 1 <= count <= 3:
    raise ValueError("count must be 1..3")
  _move(x, y)
  for _ in range(count):
    hypr.click(button)
  return f"{button} x{count} at ({x}, {y})"


@mcp.tool(annotations=ACTION)
def scroll(x: int, y: int, down: int = 0, right: int = 0) -> str:
  """Scroll at (x, y) by wheel notches; negative values scroll up / left."""
  _move(x, y)
  hypr.scroll(down * SCROLL_UNIT, right * SCROLL_UNIT)
  return f"scrolled down={down} right={right} at ({x}, {y})"


@mcp.tool(annotations=ACTION)
def drag(x1: int, y1: int, x2: int, y2: int, button: Button = "left", steps: int = 20) -> str:
  """Press at (x1, y1), move to (x2, y2), release. Requires /dev/uinput access."""
  start, end = _point(x1, y1), _point(x2, y2)
  uinput.drag([start, *interpolate(start, end, steps)], hypr.move_cursor, button)
  return f"dragged ({x1}, {y1}) -> ({x2}, {y2})"


@mcp.tool(annotations=ACTION)
def type_text(text: str) -> str:
  """Type literal text into the focused window."""
  hypr.wtype("--", text)
  return f"typed {len(text)} chars"


@mcp.tool(annotations=ACTION)
def key(combo: str) -> str:
  """Press a key combo, e.g. "Return", "ctrl+c", "ctrl+shift+t", "super+1", "F5"."""
  hypr.wtype(*wtype_args(combo))
  return f"pressed {combo}"


def main() -> None:
  """Entry point: serve over stdio. Logs go to stderr since stdout carries the protocol."""
  logging.basicConfig(level=os.environ.get("HYPR_CU_LOG", "WARNING"))
  recovered = session.discover(os.environ)
  if recovered:
    log.info("recovered session env: %s", recovered)
    os.environ.update(recovered)
  mcp.run()


if __name__ == "__main__":
  main()
