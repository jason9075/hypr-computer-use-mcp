# Lessons learned

Problems hit during development, in the order they were found. Each lists the symptom, root cause and
fix; most only surfaced through hands-on testing.

## 1. MCP hosts strip the environment

- **Symptom**: testing with the MCP SDK's stdio client, every `hyprctl` call failed with an empty stderr.
- **Root cause**: the stdio client passes only a handful of variables by default, dropping
  `HYPRLAND_INSTANCE_SIGNATURE` and `WAYLAND_DISPLAY`. On top of that, `hyprctl` writes errors to
  **stdout**, sometimes still exiting 0.
- **Fix**: recover sessions from `$XDG_RUNTIME_DIR/hypr/*/hyprland.lock`; read stdout when stderr is
  empty; treat a dispatcher as successful only when it replies `ok`.

## 2. fcitx5 turned URLs into Zhuyin

- **Symptom**: the agent typed `https://www.tldraw.com/` into the address bar and "ㄏㄩㄥ" appeared.
- **Root cause**: keystrokes from `wtype` pass through the input method.
- **Fix**: in host mode, deactivate the IME with `fcitx5-remote -c` before typing and restore its previous
  state afterwards.

## 3. A nested Hyprland on a hidden workspace stops rendering

- **Symptom**: with the nest on a hidden workspace, `grim` hung.
- **Root cause**: the host sends no frame callbacks to invisible windows, so the nested compositor draws
  no new frames and screencopy waits forever.
- **First fix**: a headless monitor `AGENT` with the nest's workspace active on it. It worked, but caused
  #4, #5 and #15.
- **Final fix**: the `render_unfocused` window rule; see #15.

## 4. A config reload moved AGENT next to the real monitor (obsolete: AGENT removed in #15)

- **Symptom**: after `nh home switch`, AGENT moved from `-10000x0` to `1920x0`, right next to the physical
  monitor, and its scale became 2.
- **Root cause**: `hyprctl keyword monitor` is runtime state, cleared by a config reload.
- **Fix**: put the monitor rule in the Hyprland config, and re-apply it on every `nest up`.

## 5. The user got trapped on an invisible monitor (obsolete: AGENT removed in #15)

- **Symptom**: the user pressed `super+1`; nothing changed on screen, the keyboard seemed dead, and they
  ended up logging out.
- **Root cause**: `super+1` was a plain `workspace 1`, and ws1 lived on AGENT, so focus moved to an
  invisible monitor. AGENT wasn't adjacent to the real monitor, so the mouse couldn't reach it either.
- **Fix**: a custom workspace-switch script pulled ws1 onto the current monitor instead. `super+0` would
  in fact have escaped (host binds take precedence over the nest), but nothing on screen said so.

## 6. Vendored bindings failed to import once deployed

- **Symptom**: everything worked locally, but the build from nixos-config failed at startup with
  `ImportError: WlOutputProxy`.
- **Root cause**: pywayland scanner output is tied to the pywayland release: 0.4.19 emits a single module,
  0.4.18 a package directory, with different exported names. nixos-config overrides nixpkgs via
  `follows` and got 0.4.18.
- **Fix**: stop vendoring; generate the bindings at Nix build time with the same pywayland, including the
  core `wayland` protocol so the two always import each other consistently. Both nixpkgs versions were
  built and used to draw.
- **Related pitfall**: hatchling honours `.gitignore` and silently dropped the generated files from the
  wheel, hence `artifacts` in `pyproject.toml`.

## 7. uinput events never reach the nest

- **Symptom**: a drag implemented with `/dev/uinput` did nothing in the nest.
- **Root cause**: uinput is a kernel input device read only by the host compositor. A nested compositor
  only receives input that the host forwards to its window.
- **Fix**: use Wayland's wlr-virtual-pointer protocol, connected directly to the nest's socket.

## 8. Absolute motion while a button is held is not a drag

- **Symptom**: dragging with `motion_absolute`, tldraw left a single dot at the start.
- **Root cause**: Hyprland appears to treat absolute virtual-pointer motion as a warp, which produces no
  drag events in clients. Without a button held, absolute motion works fine.
- **Fix**: position the start absolutely, send relative `motion` once the button is down, and correct
  against the real cursor at the end.

## 9. pywayland segfaults on teardown

- **Symptom**: the script exited with code 139.
- **Root cause**: proxies outlived the display connection and crashed when garbage-collected.
- **Fix**: destroy the pointer and the manager, roundtrip, then disconnect. In that order three
  consecutive cycles ended cleanly, so drags run inside the server process without a subprocess.

## 10. The status bar disappeared

- **Symptom**: the user's AGS bar vanished; the service crash-looped with `Failed to open display`.
- **Root cause**: on startup the nested Hyprland wrote `WAYLAND_DISPLAY=wayland-2` into the systemd/dbus
  user environment. AGS happened to restart then and attached to the nest; once the nest stopped, AGS kept
  connecting to a socket that no longer existed.
- **Fix**: restore the environment after `nest up` and after `nest down`. The `down` restore must run
  **after** the compositor stops, because the exiting nest rewrites the environment once more: it removes
  the signature but leaves its own `WAYLAND_DISPLAY`.
- **Didn't work**: Hyprland 0.54 ignores `HYPRLAND_NO_SD_VARS`.
- **Verified by**: restarting AGS while the nest runs and checking the bar appears on the host, not in the
  nest.

## 11. The nest was mistaken for the host

- **Root cause**: the nest is a Hyprland instance too, and newer than the host. With the environment
  stripped, "pick the newest instance" picked the nest.
- **Fix**: exclude the signature recorded in `nest.json` when discovering the host, covered by unit tests.

## 12. Leftover helper processes

- **Symptom**: after the nest stopped, `pgrep` still found two `Hyprland --config nest.conf` processes
  with `ppid=1`.
- **Root cause**: the nested Hyprland forks helpers that outlive it.
- **Fix**: match the nest config path in `/proc/*/cmdline` and `SIGKILL` them.

## 13. Removing an output re-centres the cursor (obsolete: AGENT removed in #15)

- **Fix**: record the cursor position before `hyprctl output remove` and move it back afterwards.

## 14. Input issues while reading YouTube recommendations

| Symptom | Cause | Status |
|---|---|---|
| `scroll` has no effect in Firefox | Probably `wlrctl` scroll events lack discrete wheel information | Open; `Page_Down` works meanwhile |
| Keys don't reach a freshly loaded page | Keyboard focus isn't on the page yet | Open; click empty page space first |
| Web page hover states don't follow the cursor | `movecursor` warps without motion events | ✅ Fixed in #18 |

## 15. A headless monitor made two compositors spin

- **Symptom**: with the nest running, the host Hyprland sat around 70% CPU and the nested one around 40%,
  over a full core together. htop shows the host as `Hyprland --watchdog-fd`, which is easy to mistake
  for the watchdog; it is the compositor itself.
- **Investigation**:

  | Attempt | Result | Lesson |
  |---|---|---|
  | AGENT from 60 Hz to 10 Hz | No effect | The refresh setting wasn't throttling anything |
  | AGENT from 1080p to 720p | 131% → 128% | Not a pixel-count problem |
  | Blur and shadow off in the nest | ~5% saved | Not a compositing-effects problem |
  | Firefox `layout.frame_rate = 15` | No effect | Video frames bypass that path |
  | Pausing the nested process | Host dropped to ~21% | Cost tracks the nest's frames |
  | **Debug overlay** | **AGENT 674 FPS, nest 492 FPS** | Root cause found |

- **Root cause**: a headless output has no vblank. The host sent a frame callback the instant it finished
  drawing AGENT, the nest drew its next frame the instant it got one, and each side kept triggering the
  other with no throttle.
- **Fix**: drop AGENT, put the nest on an ordinary hidden workspace, and launch it with the exec rule
  `render_unfocused on`. While hidden the host paces callbacks at 15 FPS, cutting total CPU from ~130% to
  ~4%.
- **Related pitfall**: `render_unfocused` only applies when the window is mapped; a later `setprop` has no
  effect, so it must be an exec rule.
- **Bonus**: #4 and #5 disappeared outright, `super+1` became a plain `workspace 1` again, and the
  switch script went away.

## 16. The nest stopped but its Firefox kept running

- **Symptom**: after restarting the nest, `open_url` produced no Firefox; the screen stayed empty.
- **Root cause**: the previous nest's Firefox didn't exit with the nested compositor. It was reparented to
  init, attached to a display that no longer existed, and still held the profile lock. Wayland clients
  don't necessarily exit with their compositor.
- **Fix**: `nest down` first finds every app in the nest by the `HYPRLAND_INSTANCE_SIGNATURE` in
  `/proc/*/environ`, sends `SIGTERM`, waits up to 5 seconds, then `SIGKILL`s survivors.
- **Related pitfall**: `pid_alive` counted zombies as alive, so `terminate` always waited out the full 5
  seconds; it now reads the state field of `/proc/PID/stat` and treats `Z` as dead.

## 17. Smaller pitfalls

| Problem | Fix |
|---|---|
| Hyprland's `--socket` only works together with `--wayland-fd` | Don't pin the socket name; identify the nested instance by its newly appeared lock file |
| A nest not started via `start-hyprland` shows a watchdog warning | `misc:disable_watchdog_warning = true` |
| Firefox hands URLs to the Firefox already running on the host | A separate profile (`--profile`): Firefox remoting is scoped to the profile, so it never reaches the host's default-profile Firefox. `--no-remote` was used at first and later dropped; see #19 |
| `focusworkspaceoncurrentmonitor` swaps workspaces | Use `moveworkspacetomonitor` |
| Hyprland keybinds ignore keystrokes from the virtual keyboard | The agent uses IPC tools such as `focus_window` |
| Every page load showed a translation prompt or a session-restore tab | The server writes a `user.js` disabling those dialogs before launching Firefox |

## 18. Clicks after a warp hit the wrong button

- **Symptom**: the waybar dock in the nest responded to the first click after a restart; later clicks on
  other buttons did nothing.
- **Root cause**: `hyprctl movecursor` only warps and sends no motion events. GTK resolves a click against
  the position of the last motion or enter event, so later clicks landed on the old position. Stale web
  page hover states had the same cause.
- **Fix**: after every warp, send a net-zero relative motion (+1px, then -1px) over wlr-virtual-pointer;
  likewise at the start of a drag. Afterwards four consecutive clicks on different dock buttons all
  worked.

## 19. Apps launched in the nest opened on the host

- **Symptom**: Firefox launched from rofi inside the nest opened its window on the host.
- **Root cause**: single-instance apps first look for an instance already running on the same user
  profile and, if found, ask it to open a window and exit. The nest shares the host's D-Bus session bus
  and home directory, so they find the host's instance. Measured: kitty (not single-instance) and Chrome,
  Obsidian and Thunar (not running on the host at the time) opened in the nest; Firefox and Discord, which
  were already running on the host, went there.
- **Fix**:
  - Firefox: use the nest profile. `open_url` used to add `--no-remote` as well, but that stopped later
    launches (e.g. from the dock) from joining the nest's instance ("Firefox is already running"), so it
    now relies on `--profile` alone. That also simplified `open_url`: with Firefox already running it no
    longer simulates `ctrl+t` and typing, it just runs `firefox --profile <nest profile> <url>` and lets
    Firefox hand the URL to the nest's instance.
  - Thunar: give it a private D-Bus with `dbus-run-session`.
  - Electron apps (Discord, Slack) use lock files in their profile directory; the only way is a separate
    profile, which is rarely worth it.

## Takeaways

- **Test every assumption for real**: almost every pitfall surfaced only through hands-on use: frame
  callbacks, absolute motion, the hijacked environment.
- **Test under the harshest conditions**: only a client that strips the environment exposed #1 and #11.
- **Verify the user was not affected**: record the host's focus, workspace and cursor before and after
  every test, not just whether the agent succeeded.
- **Deployment differs from development**: #6 only showed up when building with nixos-config's nixpkgs.
