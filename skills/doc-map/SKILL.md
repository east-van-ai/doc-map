---
name: doc-map
description: Map a Python project before reading its code. Run `doc-map print PATH` when a task reaches past one file you already have open, such as finding where something lives, checking whether something already exists, planning where new code goes, or changing code across modules. It lists every function and class with its docstring's first sentence and line number, so a ranged read replaces opening whole files or grepping for `def` and `class`. Also use it when the user asks for a map, index, or public surface of a Python codebase, or names doc-map.
---

# doc-map: YAML function/class map for Python projects

`doc-map` walks a Python project and emits a YAML manifest: every top-level and
class-level function/class, the first sentence of its docstring, and its
1-indexed line number. It is a "what exists right now" index. Hand over the
map, not the territory.

## When to run it

Reach for it before touching code you have not read this session, whenever the
task reaches past a single file: a change spanning modules, a plan that has to
say where new code goes, or any question shaped like "where does X live" or
"does this already exist". Its output is what makes a ranged read possible, so
it replaces opening files to find out what is in them.

Skip it for a task confined to a file already open in the session, or a
question one grep answers. Re-run it rather than trusting an earlier run in a
session that has since moved code around.

Not a start-of-session ritual. Running it before knowing what the task needs
is the speculative load it exists to prevent.

Never grep for `def`/`class` and hand-assemble this yourself. That misses
dotted method qualnames, docstring-derived summaries, and the filtering rules
below (tests, dunders, `__pycache__`). The tool exists to get all of that
right consistently.

## Basic usage

```bash
doc-map print PATH [--include-private] [--include-tests] [--force]
```

- PATH comes before the flags, whose order among themselves is free.
  `doc-map print . --force` is right; `doc-map print --force .` is a usage
  error.
- `--include-private` keeps single-underscore names. Dunders are skipped
  either way.
- `--include-tests` keeps test files and test directories.
- `--force` walks a root that failed the safety sniff. It does not lift the
  5000-file ceiling, which no flag lifts.
- No flag abbreviates. `--inc` is an unknown flag, not a guess at one of the
  two `--include-` flags.
- Output goes to stdout, and doc-map writes no files. A shell redirect puts
  the map on disk: `doc-map print . > map.yaml`
- `doc-map` does not read piped input; its unit of work is a directory, not a
  stream.

| Command line | Result | Exit |
| --- | --- | --- |
| `doc-map` | banner, then help | 0 |
| `doc-map print` | `print`'s page | 0 |
| `doc-map print PATH` | map on stdout | 0 |
| `doc-map print` and flags, no PATH | usage error | 1 |
| `doc-map print --force PATH` | usage error, PATH comes first | 1 |
| `doc-map print A B` | usage error, nothing after PATH | 1 |
| `doc-map print PATH`, PATH not a directory | error | 1 |
| `doc-map print PATH --nope` | argparse rejects the flag | 2 |
| `doc-map --src-root .` | argparse rejects the command | 2 |

A bare word is a question, so it prints documentation and exits 0. The test
is the word by itself: once any other token is present, the command line is
a specific request, and `doc-map print --force` with no PATH is a usage error
rather than help.

## Typical workflow

1. Run it against the project root, or a single subpackage if you only need
   part of the map:

   ```bash
   doc-map print src/
   ```

2. Read the YAML. Each top-level key is a file path relative to the root.
   Under it sit the module docstring's first sentence (`doc`), the file's
   line counts (`lines`), and a list of `def`/`doc`/`line` entries
   (`entries`). Methods carry dotted qualnames like `Foo.bar`. A `total`
   key closes the map.

3. Use it to orient. Jump straight to a definition with a ranged read or
   `vim +<line> <file>` instead of reading the whole file.

## What is filtered out by default

- Noise directories: `.git`, `__pycache__`, `.venv`, `venv`, `env`,
  `node_modules`, `.pytest_cache`, `.mypy_cache`, `build`, `dist`, `.eggs`,
  `.tox`, `.idea`, `.vscode`, and any hidden directory.
- Test files (`test_*.py`, `*_test.py`, `conftest.py`) and `test`/`tests`
  directories. Pass `--include-tests` to map them too.
- Dunder methods (`__init__`, `__repr__`, and the rest) are always skipped and
  no flag brings them back. Single-underscore names are skipped unless
  `--include-private` is passed.
- Nested defs *inside* function bodies are deliberately not descended into.
  The map stays flat, showing the public-ish surface, not every closure.

## Safety rails

These are intentional. Do not fight them.

- Refuses to walk a directory that looks like an OS root: clustered dirs like
  `bin`/`etc`/`usr`, an unusually large number of top-level entries, or a
  filesystem anchor. If the root really is right, pass `--force`.
- Hard ceiling of 5000 `.py` files mid-walk, aborting loudly rather than
  assuming a 5000-file project was meant. This one is **not** bypassed by
  `--force`. Hitting it means the root is almost certainly wrong.
- Files that fail to parse are skipped with a note to stderr, never fatal to
  the whole run.

## Exit codes

- `0`: success, and documentation. A bare word is a question, so it prints
    its page and exits 0
- `1`: any error `doc-map` raises itself (a usage slip, a root that is not
    a directory, or either guardrail refusing the walk)
- `2`: argparse's own errors (an unknown command, an unknown flag, or a bad
    value)

Every error doc-map raises goes to stderr as `doc-map: <message>`. A usage
error follows it with the usage line of the command that failed. A safety
sniff refusal follows it with the exact `--force` re-run instead.

## Why it works this way

The reasons behind the grammar, the guardrails, and the map's shape are in
[DESIGN](https://github.com/east-van-ai/doc-map/blob/main/docs/DESIGN.md).
Read it before arguing with a refusal.

## If doc-map is not installed

Check with `doc-map --version`, which names the version on PATH rather than
only its presence. If it is missing, install it without asking. It needs
Python 3.9 or newer and has no runtime dependencies:

```bash
uv tool install "git+https://github.com/east-van-ai/doc-map.git"
```

uv fetches its own Python. Without uv, use pipx, which uses the Python
already on the machine:

```bash
pipx install "git+https://github.com/east-van-ai/doc-map.git"
```

If neither uv nor pipx is on PATH, install neither. Say so, and leave that
choice to the user. If the network is unavailable but the repo is on disk,
run it from source:

```bash
PYTHONPATH=/path/to/doc_map/src python3 -m doc_map.cli print PATH
```
