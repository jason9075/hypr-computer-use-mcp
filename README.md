# hypr-computer-use-mcp

MCP server that lets an agent (Claude Code, Codex, …) use a computer on Hyprland — without
fighting you for the mouse and keyboard.

> 📖 Detailed design notes (Traditional Chinese): [docs/](docs/README.md)

## How it works: the nest

By default the agent works in a **nest**: a nested Hyprland instance running in a window on
workspace 1.

```
your Hyprland (wayland-1)
├── ws2..10 … your workspaces, your cursor, your focus — untouched
└── ws1 (usually hidden) → nest window → nested Hyprland (wayland-2)
                                          ├── own seat, cursor, keyboard focus
                                          └── agent's Firefox (persistent profile)
```

- All screenshots and input are addressed to the nested display, so nothing reaches your session.
- A hidden workspace normally stops receiving frame callbacks, which would stall the nested
  compositor. The nest window is launched with the `render_unfocused` rule, so Hyprland keeps
  driving it at `misc:render_unfocused_fps` (15) while you work elsewhere.
- Watch or take over by switching to workspace 1 like any other workspace.

Cost while hidden: about 4% CPU (host + nested). An earlier design parked the nest on a headless
monitor instead; with no vblank to pace it, the two compositors ping-ponged frames at ~500-700 FPS
for over a full core. See [docs/nest.md](docs/nest.md).

## Tools

| Tool | Notes |
|---|---|
| `start_nest` / `stop_nest` | Idempotent; `start_nest` also repairs a nest whose window was closed; `stop_nest` also closes the apps inside |
| `open_url` | Nest Firefox with a persistent profile (`$XDG_DATA_HOME/hypr-cu/firefox-profile`), so logins survive restarts; prompts like session restore and translation are pre-disabled |
| `launch` | Start any program in the session |
| `screenshot`, `list_monitors`, `list_windows`, `cursor_position` | Read-only |
| `click`, `scroll`, `mouse_move`, `drag`, `type_text`, `key`, `focus_window` | x/y are pixels of the latest screenshot |

| Primitive | Backend |
|---|---|
| screenshot | `grim -o <monitor> -s <factor>` (long edge ≤ `HYPR_CU_MAX_EDGE`) |
| move / focus / windows / lifecycle | `hyprctl` IPC |
| click / scroll | `wlrctl` (wlr-virtual-pointer) |
| drag | wlr-virtual-pointer via pywayland: press, relative motion, release |
| type / key | `wtype` (virtual-keyboard) |

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

Register with Claude Code and Codex (their configs are mutable, so this stays imperative):

```sh
just install          # registers `hypr-computer-use-mcp` from PATH
just install-dev      # or: `nix run <this checkout>` for development
```

## Customising the nest

If `$XDG_CONFIG_HOME/hypr-cu/nest.conf` exists, the nest's generated Hyprland config `source`s
it, e.g. for a wallpaper and a small dock. Host binds own SUPER and take precedence over the nest,
so clickable controls work better than keybinds:

```
exec-once = swaybg -i ~/Pictures/agent-wallpaper.png -m fill
exec-once = waybar -c ~/.config/hypr-cu/dock.json -s ~/.config/hypr-cu/dock.css
```

## CLI

```sh
hypr-computer-use-mcp                 # serve MCP over stdio
hypr-computer-use-mcp nest up        # start (or repair) the nest
hypr-computer-use-mcp nest status    # exit 1 with the reason when unusable
hypr-computer-use-mcp nest down
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `HYPR_CU_TARGET` | `nest` | `host` drives your live desktop instead (no isolation) |
| `HYPR_CU_NEST_WS` | `1` | Host workspace holding the nest window |
| `HYPR_CU_MAX_EDGE` | `1280` | Long edge of screenshots in pixels |
| `HYPR_CU_LOG` | `WARNING` | Python log level (stderr) |

## Development

```sh
direnv allow          # or: nix develop
just check            # lint + tests + nix build
just nest up         # manage the nest from the checkout
just protocols        # regenerate the vendored wlr-virtual-pointer bindings
```

## Notes

- `hyprctl` and `Hyprland` come from the host PATH so they always match the running compositor.
- MCP hosts that strip the environment are handled: sessions are recovered from
  `$XDG_RUNTIME_DIR/hypr/*/hyprland.lock`, and the nest is never mistaken for the host.
- In host mode an active fcitx5 is suspended around `type_text` / `key`; it would otherwise
  swallow the virtual keystrokes. The nest runs no input method.
- Hyprland ignores absolute virtual-pointer motion as a drag source while a button is held, so
  drags are replayed as relative motion and corrected against the real cursor.
- Hyprland keybinds are not triggered by virtual-keyboard events; use `focus_window` instead of
  WM shortcuts.

## Safety

Even in a nest, apps run as your user with your home directory and network. Only sign in to
accounts you're willing to let the agent use, and keep these tools out of auto-allow lists.
