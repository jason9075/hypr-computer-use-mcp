# Name the server is registered under in Claude Code and Codex.
name := "hypr-cu"
root := justfile_directory()

# Installed binary (e.g. via home.packages); resolved through PATH so upgrades need no re-register.
bin := "hypr-computer-use-mcp"

default:
  @just --list

# Run the MCP server over stdio (for manual debugging).
run:
  python -m hypr_computer_use.server

test:
  pytest -q

lint:
  ruff check src tests
  ruff format --check src tests

fmt:
  ruff format src tests
  ruff check --fix src tests

# Build the Nix package (also runs the test suite).
build:
  nix build "{{root}}"

check: lint test build

# Manage the agent realm (nested Hyprland on a headless monitor): up | down | status.
realm action="status":
  python -m hypr_computer_use.server realm {{action}}

# Regenerate the vendored wlr-virtual-pointer bindings (paths come from the dev shell).
protocols:
  #!/usr/bin/env bash
  set -euo pipefail
  out=src/hypr_computer_use/protocols
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  python -m pywayland.scanner -i "$WAYLAND_XML" "$WLR_VIRTUAL_POINTER_XML" -o "$tmp" 2>/dev/null
  rm -rf "$out"/wlr_virtual_pointer_unstable_v1*
  # Use pywayland's own core protocol rather than a second generated copy.
  sed 's/^from \.wayland import/from pywayland.protocol.wayland import/' \
    "$tmp/wlr_virtual_pointer_unstable_v1.py" > "$out/wlr_virtual_pointer_unstable_v1.py"
