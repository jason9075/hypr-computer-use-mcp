# hypr-computer-use-mcp

MCP server that lets an agent drive the live Hyprland session: screenshot, click, scroll,
drag, type, key combos and window focus.

| Primitive | Backend |
|---|---|
| screenshot | `grim -o <monitor> -s <factor>` (downscaled so the long edge ≤ `HYPR_CU_MAX_EDGE`) |
| move / focus / window list | `hyprctl` IPC |
| click / scroll | `wlrctl` (Wayland virtual-pointer protocol, no privileges needed) |
| type / key | `wtype` (virtual-keyboard protocol) |
| drag | evdev `/dev/uinput` device for button hold + `hyprctl movecursor` |

All x/y arguments are pixels of the **most recent screenshot**; the server maps them to
Hyprland's global logical layout (monitor offset, scale, rotation).

## Install

As a flake input (e.g. Home Manager):

```nix
inputs.hypr-computer-use-mcp = {
  url = "github:jason9075/hypr-computer-use-mcp";
  inputs.nixpkgs.follows = "nixpkgs";
};
# ...
home.packages = [ inputs.hypr-computer-use-mcp.packages.${pkgs.system}.default ];
```

Then register it with Claude Code and Codex (their config files are mutable, so this stays
imperative):

```sh
just install          # registers `hypr-computer-use-mcp` from PATH
just install-dev      # or: registers `nix run <this checkout>` for development
```

## Development

```sh
direnv allow          # or: nix develop
just check            # lint + tests + nix build
```

## Notes

- `hyprctl` is taken from the host PATH so it always matches the running compositor.
- MCP hosts that strip the environment are handled: the Hyprland instance and Wayland socket are
  recovered from `$XDG_RUNTIME_DIR/hypr/*/hyprland.lock`.
- An active fcitx5 input method is suspended around each `type_text` / `key` call, otherwise it
  would swallow the virtual keystrokes into its composition buffer.
- Hyprland keybinds are not triggered by virtual-keyboard events; use `focus_window` instead of
  WM shortcuts.

## Drag support (optional)

Atomic clicks work over the virtual-pointer protocol, but holding a button requires uinput:

```nix
hardware.uinput.enable = true;
users.users.<you>.extraGroups = [ "uinput" ];
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `HYPR_CU_MAX_EDGE` | `1280` | Long edge of screenshots in pixels |
| `HYPR_CU_LOG` | `WARNING` | Python log level (stderr) |

## Safety

This grants full keyboard/mouse control of your desktop. Keep these tools out of Claude Code's
auto-allow list, or run the agent on a dedicated workspace.
