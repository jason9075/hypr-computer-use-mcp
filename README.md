# hypr-computer-use-mcp

MCP server that lets an agent (Claude Code, Codex, …) use a computer on Hyprland — without
fighting you for the mouse and keyboard.

## How it works: the realm

By default the agent works in a **realm**: a nested Hyprland instance whose window sits on
workspace 1 of a headless monitor (`AGENT`).

```
your Hyprland (wayland-1)
├── HDMI-A-1 … your workspaces, your cursor, your focus — untouched
└── AGENT (headless, at -10000x0) → workspace 1 → nested Hyprland (wayland-2)
                                                 ├── own seat, cursor, keyboard focus
                                                 └── agent's Firefox (persistent profile)
```

Why this shape:

- Hyprland stops rendering windows on hidden workspaces, and a nested compositor only draws
  while its window is shown. Parking the realm on a headless monitor keeps it rendering while
  you work elsewhere.
- The headless monitor is not adjacent to any real one, so your cursor can never wander onto it.
- All screenshots and input are addressed to the nested display, so nothing reaches your session.

Watch or take over by bringing workspace 1 onto your monitor (see
[nixos-config `realm_ws.sh`](https://github.com/jason9075/nixos-config) for a `super+1..0`
binding that does this and parks it again).

Cost: roughly one CPU core while a realm runs (host + nested compositing), so stop it when idle.

## Tools

| Tool | Notes |
|---|---|
| `start_realm` / `stop_realm` | Idempotent; `start_realm` also repairs a realm whose window was closed |
| `open_url` | Realm Firefox with a persistent profile (`$XDG_DATA_HOME/hypr-cu/firefox-profile`), so logins survive restarts |
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

Recommended Hyprland config, so a config reload doesn't move the headless monitor next to yours:

```
monitor = AGENT, 1920x1080@60, -10000x0, 1
```

Register with Claude Code and Codex (their configs are mutable, so this stays imperative):

```sh
just install          # registers `hypr-computer-use-mcp` from PATH
just install-dev      # or: `nix run <this checkout>` for development
```

## CLI

```sh
hypr-computer-use-mcp                 # serve MCP over stdio
hypr-computer-use-mcp realm up        # start (or repair) the realm
hypr-computer-use-mcp realm status    # exit 1 with the reason when unusable
hypr-computer-use-mcp realm down
```

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `HYPR_CU_TARGET` | `realm` | `host` drives your live desktop instead (no isolation) |
| `HYPR_CU_REALM_WS` | `1` | Host workspace holding the realm window |
| `HYPR_CU_REALM_MONITOR` | `AGENT` | Name of the headless monitor |
| `HYPR_CU_REALM_MODE` | `1920x1080@60` | Headless monitor mode |
| `HYPR_CU_MAX_EDGE` | `1280` | Long edge of screenshots in pixels |
| `HYPR_CU_LOG` | `WARNING` | Python log level (stderr) |

## Development

```sh
direnv allow          # or: nix develop
just check            # lint + tests + nix build
just realm up         # manage the realm from the checkout
just protocols        # regenerate the vendored wlr-virtual-pointer bindings
```

## Notes

- `hyprctl` and `Hyprland` come from the host PATH so they always match the running compositor.
- MCP hosts that strip the environment are handled: sessions are recovered from
  `$XDG_RUNTIME_DIR/hypr/*/hyprland.lock`, and the realm is never mistaken for the host.
- In host mode an active fcitx5 is suspended around `type_text` / `key`; it would otherwise
  swallow the virtual keystrokes. The realm runs no input method.
- Hyprland ignores absolute virtual-pointer motion as a drag source while a button is held, so
  drags are replayed as relative motion and corrected against the real cursor.
- Hyprland keybinds are not triggered by virtual-keyboard events; use `focus_window` instead of
  WM shortcuts.

## Safety

Even in a realm, apps run as your user with your home directory and network. Only sign in to
accounts you're willing to let the agent use, and keep these tools out of auto-allow lists.
