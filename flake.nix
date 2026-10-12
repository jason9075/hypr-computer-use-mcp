{
  description = "MCP server exposing computer-use primitives for a Hyprland session";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        # hyprctl is deliberately NOT pinned here: it must match the running compositor's IPC,
        # so the host's hyprctl on PATH is used instead.
        runtimeTools = [ pkgs.grim pkgs.wtype pkgs.wlrctl ];

        pythonDeps = ps: [ ps.mcp ps.pywayland ];

        # Generated bindings depend on the exact pywayland release, so they are produced by the
        # same pywayland the package runs with (nixpkgs may be overridden via `follows`).
        genProtocols = pkgs.writeShellScript "gen-protocols" ''
          set -euo pipefail
          # pywayland's scanner shells out to pkg-config even when given explicit XML paths.
          export PATH=${pkgs.pkg-config}/bin:$PATH
          ${python.withPackages (ps: [ ps.pywayland ])}/bin/python -m pywayland.scanner \
            -i ${pkgs.wayland-scanner}/share/wayland/wayland.xml \
               ${pkgs.wlr-protocols}/share/wlr-protocols/unstable/wlr-virtual-pointer-unstable-v1.xml \
            -o "$1" 2>/dev/null
        '';

        app = python.pkgs.buildPythonApplication {
          pname = "hypr-computer-use-mcp";
          version = "0.1.0";
          pyproject = true;
          src = ./.;
          build-system = [ python.pkgs.hatchling ];
          dependencies = pythonDeps python.pkgs;
          preBuild = "${genProtocols} src/hypr_computer_use/protocols";
          nativeCheckInputs = [ python.pkgs.pytestCheckHook ];
          makeWrapperArgs = [ "--prefix" "PATH" ":" (pkgs.lib.makeBinPath runtimeTools) ];
          meta.mainProgram = "hypr-computer-use-mcp";
        };
      in
      {
        packages.default = app;

        apps.default = {
          type = "app";
          program = pkgs.lib.getExe app;
        };

        devShells.default = pkgs.mkShell {
          name = "hypr-computer-use-mcp";
          packages = runtimeTools ++ [
            (python.withPackages (ps: pythonDeps ps ++ [ ps.pytest ]))
            pkgs.ruff
            pkgs.just
          ];
          env.HYPR_CU_GEN_PROTOCOLS = "${genProtocols}";
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
            [ -e src/hypr_computer_use/protocols/wayland* ] 2>/dev/null \
              || "$HYPR_CU_GEN_PROTOCOLS" src/hypr_computer_use/protocols
          '';
        };
      }
    );
}
