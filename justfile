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

# Manage the agent nest (nested Hyprland on a headless monitor): up | down | status.
nest action="status":
  python -m hypr_computer_use.server nest {{action}}

# Regenerate the pywayland protocol bindings (the dev shell does this on first entry).
protocols:
  "$HYPR_CU_GEN_PROTOCOLS" src/hypr_computer_use/protocols
