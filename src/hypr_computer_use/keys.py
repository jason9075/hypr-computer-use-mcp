"""Pure translation of human key combos ("ctrl+shift+t") into wtype arguments."""

from __future__ import annotations

MODIFIERS: dict[str, str] = {
  "ctrl": "ctrl",
  "control": "ctrl",
  "shift": "shift",
  "alt": "alt",
  "altgr": "altgr",
  "super": "logo",
  "win": "logo",
  "meta": "logo",
  "cmd": "logo",
  "logo": "logo",
}

# A lone modifier is sent as its left-hand keysym.
MODIFIER_KEYSYMS: dict[str, str] = {
  "ctrl": "Control_L",
  "shift": "Shift_L",
  "alt": "Alt_L",
  "altgr": "ISO_Level3_Shift",
  "logo": "Super_L",
}

KEY_ALIASES: dict[str, str] = {
  "enter": "Return",
  "return": "Return",
  "esc": "Escape",
  "escape": "Escape",
  "tab": "Tab",
  "backspace": "BackSpace",
  "delete": "Delete",
  "del": "Delete",
  "insert": "Insert",
  "space": "space",
  "up": "Up",
  "down": "Down",
  "left": "Left",
  "right": "Right",
  "home": "Home",
  "end": "End",
  "pageup": "Page_Up",
  "pagedown": "Page_Down",
  "minus": "minus",
  "plus": "plus",
  "print": "Print",
  **{f"f{i}": f"F{i}" for i in range(1, 25)},
}


class KeyComboError(ValueError):
  """Raised when a key combo cannot be parsed."""


def _key_args(key: str) -> list[str]:
  lower = key.lower()
  if lower in KEY_ALIASES:
    return ["-k", KEY_ALIASES[lower]]
  # Single printable chars go through wtype's text path, which resolves punctuation keysyms
  # for us; "-" would be read as an option, so it needs its keysym.
  if len(key) == 1:
    return ["-k", "minus"] if key == "-" else [key]
  # Anything else is assumed to be a raw XKB keysym name (e.g. "XF86AudioMute").
  return ["-k", key]


def wtype_args(combo: str) -> list[str]:
  """Translate a combo like "ctrl+shift+t", "Return" or "super" into wtype argv (sans program).

  Raises:
    KeyComboError: on an empty combo or empty component.
  """
  # "ctrl++" means ctrl and the plus key.
  parts = combo.strip().replace("++", "+plus").split("+")
  if not combo.strip() or any(not p.strip() for p in parts):
    raise KeyComboError(f"invalid key combo: {combo!r}")
  parts = [p.strip() for p in parts]

  *mod_names, key = parts
  mods: list[str] = []
  for name in mod_names:
    mod = MODIFIERS.get(name.lower())
    if mod is None:
      raise KeyComboError(f"unknown modifier {name!r} in {combo!r}")
    mods.append(mod)

  key_mod = MODIFIERS.get(key.lower())
  key_part = ["-k", MODIFIER_KEYSYMS[key_mod]] if key_mod else _key_args(key)

  press = [arg for m in mods for arg in ("-M", m)]
  release = [arg for m in reversed(mods) for arg in ("-m", m)]
  return [*press, *key_part, *release]
