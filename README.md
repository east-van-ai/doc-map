# docmap - YAML map of a Python project

Walk a Python project and emit a YAML manifest of every function and
class, paired with the first sentence of its docstring and the line
it's defined on.

## Why

An AI coding assistant reads a codebase the expensive way. It opens
files. A file is mostly implementation, and the assistant pays for
all of it, in context window and in attention, to learn three things:
what exists, what it claims to do, and where it lives.

`docmap` hands over those three things and nothing else. Every
function and class signature, the first sentence of its docstring,
and its 1-indexed line number, as minimal YAML. A few hundred lines
standing in for a few thousand.

After that, reading gets surgical. `vim +195 src/example/cli.py` drops
a human on the exact def. An assistant does the same with a ranged
read, instead of pulling the whole file in to find one function. You
hand over the map, not the territory.

## Example output

```yaml
src/example/cli.py:
  - def: first_doc_sentence(node)
    doc: Extract the first sentence of a docstring, regardless of line breaks.
    line: 163
  - def: collect_defs(tree, include_private)
    doc: Collect top-level and class-level function/class defs with their docstrings.
    line: 195
```

- One mapping per file, paths relative to the root, files sorted
- Line numbers are 1-indexed, matching what your editor expects
- Values are quoted only when YAML needs them to be, so the common
  case stays readable
- Methods carry dotted qualnames (`Foo.bar`, `Foo.Inner.baz`)
- Nested defs inside function bodies are deliberately not descended
  into, so the map stays flat and shows the public-ish surface

## Install

`docmap` requires Python 3.9 or newer and has no runtime
dependencies: standard library only. Tested in CI on Python 3.9
through 3.14.

```bash
pipx install "git+https://github.com/east-van-ai/docmap.git"
```

## Usage

```bash
docmap print PATH [--include-private] [--include-tests] [--force]
```

- `PATH` is the directory to walk. It comes before the flags, whose
  order among themselves is free.
- Bare `docmap` prints the usage banner, and so does
  `docmap print` on its own. Walking the current directory is an
  explicit `docmap print .`
- `--include-private` includes single-underscore names. Dunders are
  always skipped.
- `--include-tests` includes files under test directories and
  `test_*.py`
- `--force` walks a root that failed the safety sniff (see below)

The map goes to stdout, so a shell redirect writes it to a file:

```bash
docmap print . > map.yaml
```

`docmap` does not read piped input: its unit of work is a directory,
not a stream.

### What it filters out by default

- `.git`, `__pycache__`, `.venv`, `venv`, `env`, `node_modules`,
  `.pytest_cache`, `.mypy_cache`, `build`, `dist`, `.eggs`, `.tox`,
  `.idea`, `.vscode`, and any hidden directory
- Test files (`test_*.py`, `*_test.py`, `conftest.py`) and directories
  named `test`/`tests`, unless `--include-tests` is passed
- Dunder methods (`__init__`, `__repr__`, etc.) always;
  single-underscore names unless `--include-private` is passed

### Safety rails

`docmap` refuses to walk a directory that looks like an OS root (a
cluster of dirs like `bin`, `etc`, `usr`; an unusually large number of
top-level entries; or a filesystem anchor like `/`). Pass `--force` if
you really mean it.

It also caps out at 5000 `.py` files mid-walk and aborts loudly, on
the assumption that crossing that ceiling means the wrong root got
passed in, not that you have a 5000-file Python project. The ceiling is
the one thing `--force` will not lift, since vouching for an odd-looking
root is not vouching for unbounded output.

## Wire it into your agent

A map you have to remember to generate is a map you will forget to
generate. It earns its keep when the assistant fetches one itself, at
the moment it needs one, and agent harnesses that read a `SKILL.md`
will do exactly that once you tell them when.

[docs/SKILL.md](docs/SKILL.md) in this repo is that file. Not a specimen
written for the README: it is the one in daily use here. Copy it to
wherever your harness keeps skills, which for Claude Code means
`~/.claude/skills/docmap/SKILL.md`, and the assistant will start
fetching the map on its own.

The `description` field at the top is the part that matters most.
It is what the assistant matches against when deciding whether to
reach for the tool, so it names situations, not features. Everything
under it is only read once the skill has already been picked. Worth
knowing if you plan to write your own for something else.

## Notes

- Works on any directory tree of `.py` files. Files that fail to
  parse are skipped with a note to stderr, never fatally.
- The YAML writer is hand-rolled to keep the tool zero-dependency

## Use of AI

Code and documentation are written in collaboration with remote and local AI; design
decisions, code review, semantic and auditory review, and final judgement stay human.

---

**East Van AI** · AI for the rest of us! · Vancouver, BC, Canada

[github.com/east-van-ai](https://github.com/east-van-ai) · <east-van-ai@proton.me>

Copyright (c) 2026 Go Nakamaru
