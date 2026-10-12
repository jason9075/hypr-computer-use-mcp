# NixOS integration

The examples follow the `taipei` machine in
[jason9075/nixos-config](https://github.com/jason9075/nixos-config).

## 1. Installing the package

`flake.nix`:

```nix
hypr-computer-use-mcp = {
  url = "github:jason9075/hypr-computer-use-mcp";
  inputs.nixpkgs.follows = "nixpkgs";
  inputs.flake-utils.follows = "flake-utils";
};
```

Home Manager:

```nix
home.packages = [ inputs.hypr-computer-use-mcp.packages.x86_64-linux.default ];
```

The package puts `grim`, `wtype` and `wlrctl` on its PATH. `hyprctl` and `Hyprland` are deliberately
**not** bundled: the host's own versions are used, since they must match the running compositor.

With `follows`, the package is built against your nixpkgs, pywayland included. The protocol bindings are
generated at build time by that same pywayland, so any version works (verified with pywayland 0.4.18 and
0.4.19).

## 2. Registering with Claude Code and Codex

Both keep mutable config files (Codex writes its own trust settings), which don't suit Home Manager, so
registration is done by command and points at the binary name on PATH:

```sh
cd ~/projects/hypr-computer-use-mcp
just install      # claude mcp add + codex mcp add, both pointing at hypr-computer-use-mcp
```

Upgrading is then just `nix flake update hypr-computer-use-mcp` followed by `nh home switch`; no
re-registration needed.

## 3. Watching the nest

The nest lives on ws1, an ordinary workspace: `super+1` to look, `super+2`…`0` to go back.

No Hyprland configuration is needed. When the nest starts, its window is placed on ws1 by an exec rule
(`workspace 1 silent`) together with `render_unfocused`, which keeps it updating at 15 FPS while hidden.

> Early versions needed a headless monitor `AGENT`, a matching monitor rule and a custom
> workspace-switch script for `super+1`. All of that was removed for performance reasons; see
> [nest.md](nest.md#why-not-a-headless-monitor-earlier-design).

## 4. Customising the nest: wallpaper and dock

If `$XDG_CONFIG_HOME/hypr-cu/nest.conf` exists, `nest up` `source`s it from the nested Hyprland config.
The `source` line is only added when the file exists, because Hyprland reports a missing `source` as a
config error.

taipei generates the file from a Home Manager module (`home/gui/agent-nest.nix`):

```nix
xdg.configFile."hypr-cu/nest.conf".text = ''
  exec-once = ${pkgs.swaybg}/bin/swaybg -i ${../../assets/agent-nest-wallpaper.png} -m fill
  exec-once = ${pkgs.waybar}/bin/waybar -c ${dockConfig} -s ${dockStyle}
'';
```

- **Wallpaper**: a nested Hyprland has a plain black background, so `swaybg` shows an agent-specific
  wallpaper with usage hints printed on it.
- **Dock**: a small `waybar` dock at the bottom of the nest:

  | Button | Command | Why |
  |---|---|---|
  | 󰈹 Firefox | `firefox --profile <nest profile> --new-window` | Shares the profile and instance with the agent's `open_url`; never reaches the host |
  | 󰆍 kitty | `kitty` | kitty isn't single-instance, so it opens in the nest as is |
  | 󰉋 Thunar | `dbus-run-session -- thunar` | Thunar is a D-Bus single instance; a private bus keeps it out of the host's Thunar |
  | 󰀻 Launcher | `rofi -show drun` | |
  | 󰅖 Close | `hyprctl dispatch killactive` | There is no `super+q` inside the nest (on the host it closes the whole nest) |

  The first attempt used a keybind (`alt+f`). It was replaced by the dock because host binds own SUPER and
  take precedence over the nest, and clickable controls are easier to discover.
- **Caveat**: a single-instance app launched from rofi opens on the host if the host already runs one
  (Firefox, Discord, ...). The dock buttons above exist to avoid exactly that; see
  [lessons-learned](lessons-learned.md#19-apps-launched-in-the-nest-opened-on-the-host).
- **Closing apps**: use the dock's 󰅖, or the app's own ✕ / `ctrl+q`. Pressing `super+q` on ws1 closes the
  nest's outer window; the apps inside keep running in the background until `nest down`.

## 5. Status icon

The ws1 icon is a robot 󰚩 that changes colour with the nest's state:

| State | Condition | Colour |
|---|---|---|
| No nest | No `nest.json`, or its compositor PID is gone | Default |
| Nest idle | Nest alive, no tool call in the last 20 s | Yellow |
| **Agent acting** | A tool call within the last 20 s | **Pulsing green** |

How it works:

- **Server**: every tool call that resolves the nest touches `$XDG_RUNTIME_DIR/hypr-cu/activity`;
  `nest down` deletes it.
- **AGS**: every 0.5 s it reads `nest.json` with Gio, checks the PID is alive, compares the mtime of
  `activity`, and turns the result into CSS classes on the ws1 button (`nest-idle`, `nest-active`). The
  tooltip shows the state too.

The 20-second window exists because agents think between tool calls; a shorter one would make the icon
flicker mid-task.

During development it turned out the AGS code assumed `focusedWorkspace` is never null. It is null for a
moment while a monitor is removed, and the resulting exception froze the workspace buttons' state. A null
check now guards it.

## 6. No uinput needed

Early versions implemented drag with `/dev/uinput`, which required adding the user to the `uinput` group.
Since switching to wlr-virtual-pointer that is no longer needed.

## Troubleshooting

### The status bar disappeared

The nest's variables were left in the systemd user environment. Current versions restore it
automatically; if it happens anyway:

```sh
systemctl --user set-environment WAYLAND_DISPLAY=wayland-1 \
  HYPRLAND_INSTANCE_SIGNATURE=$(hyprctl instances -j | jq -r '.[0].instance')
systemctl --user reset-failed ags && systemctl --user restart ags
```

### The nest is stuck, Firefox won't open, or its state is unclear

```sh
hypr-computer-use-mcp nest status    # exit 0 when healthy; otherwise exit 1 with the reason
hypr-computer-use-mcp nest down      # full cleanup: apps inside, compositor, helpers, environment
hypr-computer-use-mcp nest up        # start again
```

### `Hyprland --watchdog-fd` uses lots of CPU in htop

That is the host compositor itself, not the watchdog (`start-hyprland` is the watchdog). With a hidden
nest the host should sit at a few percent; if it is much higher, check you aren't running an old version
that still used the `AGENT` headless monitor.
