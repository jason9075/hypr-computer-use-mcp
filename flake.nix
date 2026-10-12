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

        pythonDeps = ps: [ ps.mcp ps.evdev ];

        app = python.pkgs.buildPythonApplication {
          pname = "hypr-computer-use-mcp";
          version = "0.1.0";
          pyproject = true;
          src = ./.;
          build-system = [ python.pkgs.hatchling ];
          dependencies = pythonDeps python.pkgs;
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
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          '';
        };
      }
    );
}
