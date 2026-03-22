# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build

Each talk is a Nix package. Build with quotes around the `#` to avoid shell comment interpretation:

```bash
nix build '.#2026-03-28' --out-link result
```

Output PDF is at `result/<name>.pdf`.

## Format

Formatting is handled by treefmt (typstyle for `.typ`, nixfmt for `.nix`) via pre-commit hooks. Run manually:

```bash
nix fmt
```

## Adding a New Talk

1. Create a date-based directory at root: `YYYY-MM-DD/main.typ`
2. Import shared themes via relative path: `#import "../themes/poster.typ": *`
3. Register in `flake.nix` under `packages`:
   ```nix
   "YYYY-MM-DD" = buildTypstProject {
     name = "YYYY-MM-DD";
     type = "article";  # or "slide"
   };
   ```
4. Add a `README.md` in the talk directory (in English, follow antfu/talks format)
5. Update root `README.md` with the new entry

## Architecture

- **`YYYY-MM-DD/`** — Each talk as a date-named directory containing `main.typ` and `README.md`
- **`themes/`** — Shared Typst theme files (e.g., `poster.typ` for A0 poster layout)
- **`flake.nix`** — Nix flake with `buildTypstProject` helper that compiles Typst to PDF. Supports `"article"` and `"slide"` types (slides additionally run `polylux2pdfpc`)
- Fonts (EB Garamond, BIZ UDPGothic, Noto CJK, HackGen, Garamond Math) and Typst packages are pinned via Nix

## Conventions

- READMEs are in English
- Directory naming follows `YYYY-MM-DD` format (matches talk date)
