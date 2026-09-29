{
  description = "pulseq-reports: development shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      # Attributes shared by every devShell for this project.
      mkDevShell =
        pkgs: packages:
        pkgs.mkShellNoCC (
          {
            inherit packages;
            # uv builds the venv on the Nix python and never downloads one.
            UV_PYTHON = "${pkgs.python312}/bin/python3";
            UV_PYTHON_DOWNLOADS = "never";
          }
          // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
            # PyPI manylinux wheels (numpy) load libstdc++ and zlib, which the
            # Nix python does not have on its library path.
            LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
            ];
          }
        );
    in
    {
      devShells = forAllSystems (pkgs: {
        default = mkDevShell pkgs [
          pkgs.python312
          pkgs.uv
          pkgs.gh
          pkgs.git
          pkgs.jq
          pkgs.nodejs
          pkgs.shellcheck
        ];
        # A smaller shell for CI: only the tools that scripts/check needs.
        ci = mkDevShell pkgs [
          pkgs.python312
          pkgs.uv
          pkgs.nodejs
          pkgs.shellcheck
        ];
        # The tools of scripts/rf_references.py, which writes the external reference
        # fixtures of tests/test_rf_references.py. CI does not use this shell: it only
        # reads the fixtures. MATLAB Pulseq is pinned to one commit by its hash.
        rf-references =
          (mkDevShell pkgs [
            pkgs.python312
            pkgs.uv
            pkgs.octave
          ]).overrideAttrs
            {
              MATLAB_PULSEQ = pkgs.fetchFromGitHub {
                owner = "pulseq";
                repo = "pulseq";
                rev = "c7469123c2f381f065986e6cc3a7d09730ed16ef";
                hash = "sha256-Q9XjlghUUVDb9ZLs6UQoh6Q/n+KhrrVlyhcIsVzuuig=";
              };
              MATLAB_PULSEQ_REV = "c7469123c2f381f065986e6cc3a7d09730ed16ef";
            };
      });
    };
}
