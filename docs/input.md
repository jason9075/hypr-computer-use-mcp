# Screenshots and input

## Coordinates

The model sees a downscaled screenshot, so every x/y argument is **a pixel in the most recent
screenshot**. The server maps it to Hyprland's global logical coordinates:

```
screenshot px ──(÷ factor)──> monitor-local logical ──(+ monitor position)──> global logical
```

`Viewport` in `geometry.py` holds everything the mapping needs:

```python
@dataclass(frozen=True)
class Viewport:
  monitor: str
  origin_x: int     # monitor position in the global layout
  origin_y: int
  logical_w: int    # logical size (scale divided out, rotation applied)
  logical_h: int
  factor: float     # screenshot pixels per logical pixel
```

- **Downscaling**: `factor = min(1, MAX_EDGE / long edge)`, with the long edge capped at 1280px by
  default. High-resolution screenshots cost many tokens and make the model's coordinates less accurate.
- **HiDPI**: sizes are divided by the monitor's `scale` first.
- **Rotation**: for odd `transform` values (90° / 270°) width and height swap.
- **Bounds checking**: coordinates outside the screenshot return an error rather than clicking somewhere
  unexpected.

Screenshots use `grim -o <monitor> -s <factor>`. `grim`'s `-s` scales relative to the logical size, so
the image comes out at exactly `Viewport.image_size` with no Pillow resize needed.

Each session (host or nest) remembers the `Viewport` of its own last screenshot, so coordinates from one
never leak into the other.

## Pointer: warp, then real motion

```
hyprctl dispatch movecursor X Y    # warp to global logical coordinates
virtual pointer: motion(+1, 0), motion(-1, 0)
wlrctl pointer click left          # click via wlr-virtual-pointer
wlrctl pointer scroll DY DX        # one wheel notch = 15 axis units
```

`movecursor` only **warps**: it sends no motion events, so clients keep a stale pointer position. Hover
states don't update, and GTK resolves a following click against the last widget the pointer entered
(waybar dock buttons after the first click did nothing). Every warp is therefore followed by a net-zero
relative motion over wlr-virtual-pointer.

`wlrctl` speaks Wayland's virtual-pointer protocol and **needs no root, uinput or daemon**, which is why it
was chosen over `ydotool`.

## Keyboard: `wtype`

- `type_text`: `wtype -- "text"`, Unicode included (`→`, `🎯`, CJK).
- `key`: `keys.py` turns `"ctrl+shift+t"` into `wtype -M ctrl -M shift t -m shift -m ctrl`.
  - Single characters go through wtype's text path, which resolves punctuation keysyms itself.
  - `-` would be parsed as an option, so it is sent as the keysym `minus`; `ctrl++` means ctrl plus the
    plus key.
  - Common aliases: `enter`, `esc`, `backspace`, `pageup`, `f1`…`f24`, and `super` / `win` / `cmd` (all
    mapped to `logo`).

### fcitx5 swallows keystrokes (host mode only)

Keystrokes from `wtype` pass through the input method. With fcitx5's Zhuyin active, typing `https://...`
produced "ㄏㄩㄥ". In host mode the server therefore deactivates the IME with `fcitx5-remote -c` before
typing and, if it was active, restores it with `fcitx5-remote -o` afterwards. The nest runs no input
method, so it doesn't need this.

### Limitation: Hyprland keybinds ignore the virtual keyboard

When `wtype` sends `super+m`, Hyprland doesn't trigger the bound action. To switch windows the agent
should use IPC tools such as `focus_window`, not WM shortcuts.

## Drag: wlr-virtual-pointer + pywayland

A drag needs press → move → release, and `wlrctl` only offers an atomic click. How this evolved:

| Attempt | Result |
|---|---|
| evdev `/dev/uinput` | ❌ uinput is a kernel device: its events only reach the **host** seat, never the nest; it also needs extra group permissions |
| Virtual pointer + `motion_absolute` | ❌ left a single dot at the start; the movement wasn't treated as a drag |
| Virtual pointer + relative `motion` | ✅ tldraw rectangles, arrows, pen strokes and GIMP brush strokes all correct |

### Why absolute motion fails

Without a button held, `motion_absolute` moves the cursor correctly. With a button held, apps receive no
movement. Hyprland appears to treat absolute virtual-pointer motion as a warp, and warps produce no
client-side drag events. With relative motion the cursor lands exactly and apps see a real drag.

### Implementation (`vpointer.py`)

```
1. hyprctl movecursor to the start      ← absolute positioning (no button held, so fine)
2. motion(+1, 0), motion(-1, 0)         ← let the client see the warp before the press
3. button(BTN_LEFT, pressed)
4. relative motion(dx, dy) along the path, 15 ms per step
5. read the real cursor and correct any drift  ← guards against pointer acceleration
6. button(BTN_LEFT, released)           ← in a finally block, so it is always released
```

The connection uses the socket's **absolute path** (`$XDG_RUNTIME_DIR/wayland-2`), independent of the
server process's own environment.

Teardown order matters: destroy the pointer and the manager, roundtrip, then disconnect. In any other
order pywayland segfaults while collecting the proxies.
