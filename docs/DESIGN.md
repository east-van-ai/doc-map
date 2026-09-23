# docmap DESIGN

## Architecture

`docmap` requires Python 3.9 or newer and uses the standard library
only, with no runtime dependencies (`ast`, `argparse`,
`importlib.metadata`, `pathlib`, `re`, `sys`). The hand-rolled YAML
writer exists precisely to keep it that way. The GitHub CI matrix
tests Python 3.9 through 3.14.

The whole implementation is one module, `src/docmap/cli.py`: pure
functions with one job each, plus a `main()` that wires them into a
pipeline. Data is plain dicts and strings; the only state is the
filesystem being read.

One module is a decision, not a leftover. The usual split gives a CLI
a file for the parser, a file per command, and a short entry point,
which is what keeps a many-command tool readable. docmap has one
command that does work and one pipeline. Cutting that pipeline across
three files would cost imports and indirection to buy back nothing.
The file stays whole past the point where a line budget would call for
the split.

The walk pays the visible price. `walk_project` exits on the file
ceiling rather than returning a code up to `main`, because the count
crosses deep inside the rglob loop and threading a result back out
would put a return path through every caller for one refusal. The
exit code is 1 either way and the message still reads `docmap: ...`
on stderr, so nothing about the contract changes.

docmap writes nothing. It reads, parses, and prints; the map arrives
on stdout, and a shell redirect takes it from there. The guardrails
below still matter, since a wrong PATH costs time and yields a useless
map, but with no write path it can never cost more than that.

## The Guardrails

docmap's distinguishing concern. The business logic is a read-only
walk, but the walk is aimed by a single PATH argument, and the cost of
aiming it wrong is grinding through an OS root or a monorepo parent for
minutes, then emitting a useless map of the world. The guardrails exist
to make the wrong invocation loud and cheap instead of slow and silent.

1. **Root sniff** (`smells_like_system_root`). Refuses to walk a root
   that doesn't look like a project, on three heuristics:
   - A *cluster* of OS-root marker names (`bin`, `etc`, `usr`,
     `Library`, `Windows`, ...) at the top level. One alone is
     normal, since plenty of projects have a `lib/`. Three or more
     together at the same level is the real signal.
   - Thirty or more top-level entries. Hand-built project roots are
     small; home directories and drive roots are not.
   - The root is a filesystem anchor (`/`, a drive, a volume).

   `--force` is the single escalation past the sniff, the same
   posture as a plan/apply split: the default invocation is safe,
   the risky step costs one deliberate token. Refusal, not a
   confirmation prompt. docmap is built to run non-interactively at
   session start and inside scripts, where a prompt would hang, and
   a refusal carrying the exact re-run flag is script-friendly and
   just as explicit.

2. **File ceiling.** A hard cap of 5000 `.py` files counted mid-walk.
   This is the second net, for wrong roots that pass the sniff: a
   vendored `node_modules`-style leak, or a parent directory holding
   fifty checkouts. Crossing it means "this almost certainly isn't a
   single project", so docmap aborts loudly (exit 1) rather than
   grind on. It is deliberately *not* overridable by `--force`;
   `--force` vouches for the root looking odd, not for unbounded
   output.

3. **Default filters.** VCS/cache/build/venv directories, hidden
   files and directories, and test files are skipped by default.
   `SKIP_DIRS` and `is_test_file` hold the lists. This is a guardrail
   in the small: the map is meant to show a project's own public-ish
   surface, and every filtered entry is noise that would drown it.

   Membership in `SKIP_DIRS` is narrow on purpose. Only names that
   cannot plausibly hold hand-written source qualify: VCS, caches,
   build output, virtualenvs, editor state. A name does not earn a
   place merely because this project happens to use it that way.
   `data` is the counter-example that put the rule here. It is an
   ordinary package name, so skipping it drops real source from the
   map.

## The Walk/Extract Pipeline

`main()` runs: a bare word -> parse args -> grammar guards -> root
checks (is a directory, root sniff) -> `walk_project` -> `dump_yaml` ->
stdout. The grammar guards read the slots of the command's row in
`COMMANDS`, one row per command word. The bare-word check comes before
the parser is built, so the banner never depends on argparse.

- `walk_project` does a sorted `rglob("*.py")` under the root,
  applying the filters (`should_skip_dir`, `is_test_file`, hidden
  checks) and the file ceiling. Each surviving file is read and
  `ast.parse`d; a file that fails to parse or decode is skipped with
  a note to stderr, never fatally, since one broken file shouldn't
  cost the map of the other two hundred.
- `collect_defs` walks the AST of one module: top-level and
  class-level defs only, with dotted qualnames for methods
  (`Foo.bar`, `Foo.Inner.baz`). It deliberately does **not** descend
  into function bodies, because nested defs are implementation
  detail. The map stays flat, showing the public-ish surface. Dunders
  are always skipped; single-underscore names are skipped unless
  `--include-private`.
- `first_doc_sentence` extracts the first sentence of a docstring
  regardless of line breaks, splitting on `.`, `!`, or `?` followed
  by whitespace or end-of-string. A one-paragraph docstring yields
  one sentence, not the whole block.

## YAML Output Shape

One mapping per file (path relative to the root), each holding a list
of entries:

```yaml
src/example/cli.py:
  - def: collect_defs(tree, include_private)
    doc: Collect top-level and class-level function/class defs with their docstrings.
    line: 195
  - class: Walker
    doc: ""
    line: 40
```

`dump_yaml` and `yaml_escape` are hand-rolled: the zero-dependency
rule is worth more than full YAML generality, and the output grammar
is tiny, being keys, two-space indented list items, and scalar
strings. `yaml_escape` quotes only when it must (YAML-significant
characters or surrounding whitespace), so the common case stays clean
to read. Files with no surviving entries are omitted entirely.

## The Command Line

`docs/CLI.md` states the surface: the grammar, the accepted command
lines, the flags, and the exit codes. This section holds the decisions
under it.

Positions are decided, not inferred. Argparse from Python 3.12 on
back-fills a trailing optional positional from a token after any
number of flags, so trusting it would let the accepted grammar drift
from the documented one. docmap reads the tokens ahead of the first
flag instead, and takes PATH from there.

Walking the current directory costs one explicit token, `docmap print
.`. That echoes the guardrail posture above: the harmless invocation is
the default, and the filesystem tree is asked for by name.

A bare word is a question and gets documentation. One command in one
file means one document, so bare `docmap` and bare `docmap print` both
print the module docstring, which is the usage banner. It already names
the command, the argument, and every flag, and a second copy beside it
would drift.

The test is the token itself, `docmap` alone or `print` alone, never
"PATH is missing". Once any other token is present the user asked for
something specific, and answering with help would hide the mistake.

`version` is the case that shows why the test is written that way. It is
two tokens, the same shape as bare `print`, but it takes no argument.
Nothing about it is incomplete, so it answers with the version line
rather than the banner. A count of tokens could not tell the two apart.

No piped input is a documented rule, not an enforced one. `isatty()` answers
"is a human here", which is right for choosing how to present an answer
and wrong for deciding what the answer is. `/dev/null` arrives from
cron, from a subprocess, and from a test runner, and reads as a pipe
under that test, so one command line would print help from a shell and
fail under nohup. Bare `docmap` prints the banner and exits 0, whatever
stdin is.

A guardrail refusal prints the exact `--force` re-run hint where a
usage error would print the usage line. The fix there is a flag, not a
different grammar.

## Use of AI

Both the use of AI and its disclosure are deliberate. Code and
documentation in this project are written in collaboration with
Artificial Intelligence (AI). The division of labour: the AI explores,
challenges assumptions and edge cases, and drafts; the human
initiates, drafts the designs, explores alongside the AI, reviews
every change, and decides what gets committed.

---

**East Van AI** · AI for the rest of us! · Vancouver, BC, Canada

[github.com/east-van-ai](https://github.com/east-van-ai) · <east-van-ai@proton.me>

Copyright (c) 2026 Go Nakamaru
