# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.3.4] - 2026-09-23

### Changed

- A stray word after `docmap version` reads `version takes nothing after it`,
  the same wording the `print` slot errors use
- `README.md` carries the current Use of AI block, and its `vim` example
  points at the example output's own path
- `docs/DESIGN.md` lists the pipeline in the order `main()` runs it

## [0.3.3] - 2026-09-16

### Changed

- `DESIGN.md` and `SKILL.md` moved into `docs/`
- The command surface has its own document, `docs/CLI.md`: the grammar,
  the accepted command lines, the flags, and the exit codes

### Fixed

- A stray word after `docmap version` prints the `version` usage line, not
  the `print` grammar

## [0.3.2] - 2026-09-03

### Added

- `docmap version` prints the program name and the installed version,
  then exits 0. A stray word after it is a usage error, exit 1

### Changed

- Neither version spelling is advertised. Both are gone from the usage
  banner, from `README.md`, and from `DESIGN.md`'s grammar table.
  DESIGN's prose names `version` once, where accuracy demands it

## [0.3.1] - 2026-08-24

### Added

- `docmap --version` prints the program name and the installed
  version, then exits 0. It sits on `docmap` itself, not on `print`

## [0.3.0] - 2026-08-19

### Changed

- **Breaking:** the CLI grammar is now `docmap print PATH [--flags]`.
  The command word comes first, PATH second, and flags after PATH. The
  old `--src-root PATH` option is gone
- Bare `docmap` prints the usage banner and exits 0 whatever stdin is,
  instead of erroring when stdin is a pipe. `docmap print` on its own
  prints the same banner
- `DESIGN.md` leads with the engine now. The CLI grammar sits below it
  and opens with a table of every accepted command line

### Removed

- **Breaking:** `--out FILE`. docmap prints the map to stdout, and a
  shell redirect writes it: `docmap print . > map.yaml`

## [0.2.1] - 2026-08-19

### Added

- `SKILL.md`, a ready-to-copy agent skill definition, shipped in the
  public carve-out

### Changed

- README leads with the context-window case for handing over a map,
  and points at `SKILL.md` for wiring docmap into an agent
- Usage banner trimmed: no filename header, no pointer to `DESIGN.md`
  and `git log`, and exit codes listed one per line. README, DESIGN,
  and `SKILL.md` list them the same way

### Fixed

- Directories named `data` are no longer skipped. `data/` is an
  ordinary package name, and skipping it dropped real source from the
  map without any documentation saying so

## [0.2.0] - 2026-08-18

### Changed

- **Breaking:** the walk target is now the named option `--src-root PATH`
  instead of the bare `ROOT` positional, and flag order is free. Walking
  the current directory is `docmap --src-root .`
- Dev dependencies live in a `[dependency-groups]` block in
  `pyproject.toml`, with `black` and `ruff` pinned. Install with
  `pip install -e . --group dev`
- Table-of-contents blocks dropped from `README.md`, `DESIGN.md`, and
  `CLAUDE.md`
- Install and homepage URLs point at `east-van-ai/docmap`. The install
  line no longer tracks a `stable` branch

### Removed

- `RELEASING.md`
- `requirements.txt` and `requirements-dev.txt`

## [0.1.0] - 2026-07-18

### Added

- Abstract Syntax Tree (AST) based extraction of top-level and class-level
  functions/methods, with first-sentence docstrings and line numbers
- Hand-rolled minimal YAML writer (no external dependencies)
- Default noise filtering: VCS/cache/build dirs, hidden dirs, test files
- OS-root sniff test with `--force` override
- Mid-walk file count ceiling (5000) as a second safety net
- `--include-private`, `--include-tests`, `--out` flags
- pytest suite covering docstring extraction, arg formatting, YAML
  escaping, nested class/method qualnames, filtering, safety checks, and
  CLI end-to-end behavior
- Packaged for `pipx install`
- Nested classes have dotted qualnames (e.g. Foo.Inner.baz)
- `DESIGN.md` (architecture, CLI grammar, guardrail rationale) and
  `RELEASING.md` (stable-branch release model)

### Changed

- CLI grammar reworked: bare `docmap` on a TTY prints the
  usage banner and exits 0 (walking the current directory is an explicit
  `docmap .`); bare `docmap` with piped stdin is a usage error (docmap
  takes no piped input); flags-first/root-last argument order is
  enforced; errors go to stderr as `docmap: ...` plus a usage line
- Exit codes normalized to `0` success, `1` for every docmap-raised
  error (usage, bad root, both guardrail refusals; previously `3` for
  the root sniff and `2` for the file ceiling), `2` reserved for
  argparse's own errors
- Python floor widened from >=3.14 to >=3.9; CI now runs a 3.9-3.14
  matrix with `ruff check` and `black --check` on every push
- Tests split by layer into `test_extraction.py`, `test_walking.py`,
  and `test_cli_integration.py`, with a subprocess `run_cli` fixture
  invoking `python -m docmap.cli`
- README restructured (Why / Example output /
  Install / Usage / Notes / Use of AI); install now points at the
  `stable` branch
