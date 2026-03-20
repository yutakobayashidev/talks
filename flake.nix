{
  description = "A Nix-flake-based Typst development environment";

  inputs = {
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1";
    flake-parts.url = "github:hercules-ci/flake-parts";
    treefmt-nix.url = "github:numtide/treefmt-nix";
    pre-commit-hooks-nix.url = "github:cachix/pre-commit-hooks.nix";
    typst-packages = {
      url = "github:typst/packages";
      flake = false;
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.treefmt-nix.flakeModule
        inputs.pre-commit-hooks-nix.flakeModule
      ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      perSystem =
        { pkgs, config, ... }:
        let
          garamond-math = pkgs.stdenvNoCC.mkDerivation {
            pname = "garamond-math";
            version = "2019-08-16";
            src = pkgs.fetchzip {
              url = "https://mirrors.ctan.org/fonts/garamond-math.zip";
              hash = "sha256-rWdPyi+w5pT4TE2v473o3vM9pdJulutRqvw8/6CzqcY=";
            };
            dontBuild = true;
            installPhase = ''
              mkdir -p $out/share/fonts/opentype
              cp $src/Garamond-Math.otf $out/share/fonts/opentype/
            '';
          };

          typstPackagesCache = pkgs.stdenvNoCC.mkDerivation {
            name = "typst-packages-cache";
            src = pkgs.symlinkJoin {
              name = "typst-packages-src";
              paths = [ "${inputs.typst-packages}/packages" ];
            };
            dontBuild = true;
            installPhase = ''
              mkdir -p $out/typst/packages
              cp -LR --reflink=auto --no-preserve=mode -t $out/typst/packages $src/*
            '';
          };

          buildTypstProject =
            { name, type }:
            let
              _ =
                assert builtins.elem type [
                  "article"
                  "slide"
                ];
                null;
            in
            pkgs.stdenv.mkDerivation {
              inherit name;
              src = ./.;
              nativeBuildInputs =
                with pkgs;
                [
                  typst
                  eb-garamond
                  noto-fonts-cjk-serif
                  noto-fonts-cjk-sans
                  hackgen-font
                ]
                ++ [ garamond-math ]
                ++ pkgs.lib.optionals (type == "slide") [ polylux2pdfpc ];

              buildPhase = ''
                export TYPST_FONT_PATHS="${pkgs.eb-garamond}/share/fonts/opentype"
                export TYPST_FONT_PATHS="$TYPST_FONT_PATHS:${pkgs.noto-fonts-cjk-serif}/share/fonts/opentype/noto-cjk"
                export TYPST_FONT_PATHS="$TYPST_FONT_PATHS:${pkgs.noto-fonts-cjk-sans}/share/fonts/opentype/noto-cjk"
                export TYPST_FONT_PATHS="$TYPST_FONT_PATHS:${pkgs.hackgen-font}/share/fonts/hackgen"
                export TYPST_FONT_PATHS="$TYPST_FONT_PATHS:${garamond-math}/share/fonts/opentype"
                export TYPST_PACKAGE_PATH="${typstPackagesCache}/typst/packages"

                typst compile --root . ${name}/main.typ

                ${pkgs.lib.optionalString (type == "slide") ''
                  polylux2pdfpc ${name}/main.typ
                ''}
              '';

              installPhase = ''
                mkdir -p $out
                cp ${name}/main.pdf $out/${name}.pdf
                ${pkgs.lib.optionalString (type == "slide") ''
                  cp ${name}/main.pdfpc $out/${name}.pdfpc
                ''}
              '';
            };
        in
        {
          treefmt.config = {
            projectRootFile = "flake.nix";
            programs.typstyle.enable = true;
            programs.nixfmt.enable = true;
          };

          pre-commit = {
            check.enable = false;
            settings.hooks = {
              treefmt = {
                enable = true;
                package = config.treefmt.build.wrapper;
              };
            };
          };

          devShells.default = pkgs.mkShell {
            shellHook = ''
              ${config.pre-commit.installationScript}
            '';
            packages = with pkgs; [
              typst
              typstyle
              tinymist
            ];
          };

          packages = {
            "2026-03-28" = buildTypstProject {
              name = "2026-03-28";
              type = "article";
            };
          };
        };
    };
}
