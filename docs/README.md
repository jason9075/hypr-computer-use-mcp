# hypr-computer-use-mcp design notes

How an agent (Claude Code, Codex) uses a computer on Hyprland **without fighting you for the mouse and
keyboard**.

![A smiley face the agent drew in GIMP inside the nest](images/gimp-smiley.png)

> Above: the agent opened GIMP inside the nest, created a canvas and drew a smiley face with 70 `drag`
> calls. The user's focus, workspace and cursor were never touched.

## Reading order

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Overall architecture, module responsibilities, the life of a tool call |
| [nest.md](nest.md) | Why a nested Hyprland, how it keeps rendering while hidden, lifecycle |
| [input.md](input.md) | Screenshot coordinates; how click, scroll, typing and drag are implemented |
| [nixos-integration.md](nixos-integration.md) | Flake packaging, registration, wallpaper and dock, status icon, troubleshooting |
| [lessons-learned.md](lessons-learned.md) | Every pitfall hit during development, with root cause and fix |

## Naming

**nest** is the agent's own nested Hyprland. Early versions called it a *realm*; it was renamed to avoid
confusion with [0xmiki/hypr-realm](https://github.com/0xmiki/hypr-realm), a Hyprland fork. This project
runs on stock Hyprland and does not modify the compositor.

## In one paragraph

The agent is confined to a **nested Hyprland (the nest)** in a window on workspace 1. The
`render_unfocused` window rule keeps it updating at 15 FPS while hidden, and every screenshot and input
event is addressed to the nest's Wayland socket, so nothing ever reaches the user's session. While
hidden, the nest costs about 4% CPU in total.
