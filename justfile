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

# Register the PATH-installed server with Claude Code and Codex.
install: (register bin)

# Register this checkout via `nix run` (before the package is installed system-wide).
install-dev: build (register 'nix run ' + quote(root))

# (Re-)register `cmd` with both agents; removing first keeps this idempotent.
register cmd:
  -claude mcp remove --scope user {{name}} 2>/dev/null
  claude mcp add --scope user {{name}} -- {{cmd}}
  -codex mcp remove {{name}} 2>/dev/null
  codex mcp add {{name}} -- {{cmd}}

uninstall:
  -claude mcp remove --scope user {{name}}
  -codex mcp remove {{name}}
