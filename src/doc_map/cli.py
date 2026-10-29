"""
# ==============================================
# East Van AI -- AI for the rest of us!
# https://github.com/east-van-ai/doc-map
# contact: east-van-ai@proton.me
# license: MIT
# ==============================================

        doc-map

doc-map walks a Python project and prints a YAML map of it: every function
and class with the first sentence of its docstring and its line, each file's
own docstring and line counts, and a total. Hand over the map, not the
territory. Print one with `doc-map print PATH`.

Run a command with nothing after it for its own page.

piped input:
    doc-map reads none.

exit codes:
    0:     success, and documentation
    1:     doc-map's own error: a usage slip, a root that is not a directory,
           or either guardrail refusing the walk
    2:     an unknown command, an unknown option, or a bad value
"""

import argparse
import ast
import io
import re
import sys
import tokenize
from collections import namedtuple
from importlib import metadata
from pathlib import Path

PROG = "doc-map"

MONOCHROME = {"color": False} if sys.version_info >= (3, 14) else {}
"""argparse's `color=` switch, from 3.14. Older versions print no colour."""

PATHS = """\
paths:
  PATH      the directory to walk. Use `.` for the current directory.
  PATH comes right after COMMAND, then options in any order."""
"""The section `doc-map --help` closes with, since PATH belongs to no one command."""

# Argparse hardcodes 2 in `ArgumentParser.error()`, which calls `sys.exit`
# itself, so EXIT_ARGPARSE is never returned, only asserted against.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ARGPARSE = 2

# Directories we never want to walk into. Only names that cannot plausibly
# hold hand-written source belong here.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
    ".eggs",
    ".tox",
    ".idea",
    ".vscode",
}

# Top-level directory names that, when clustered together at a root,
# strongly suggest "this is an OS root" rather than "this is a project."
# Seeing a couple of these alone is normal (a project might have a "lib"
# folder); seeing several together at the same level is the real signal.
OS_ROOT_MARKERS = {
    "bin",
    "sbin",
    "etc",
    "proc",
    "sys",
    "usr",
    "lib",
    "lib64",
    "boot",
    "dev",
    "opt",
    "var",
    "mnt",
    "media",
    "Library",
    "System",
    "Applications",
    "Volumes",
    "Windows",
    "Program Files",
    "Program Files (x86)",
}

# If a root directory contains this many top-level entries or more,
# it's almost certainly not a hand-built project directory.
SUSPICIOUS_TOPLEVEL_COUNT = 30

# Hard ceiling on total .py files found mid-walk. If we cross this,
# something is wrong (wrong root, accidental vendor/ or node_modules
# leak, etc.) and we bail loudly rather than grind on for ten minutes.
MAX_PY_FILES = 5000

# The four line counts, in the order the YAML prints them.
LINE_COLUMNS = ("code", "blank", "comments", "docstrings")

# Tokens that carry no code. Comments are counted on their own.
LAYOUT_TOKENS = {
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}


def smells_like_system_root(root: Path) -> str:
    """Return a non-empty reason string if root looks like an OS root,
    or an empty string if it looks like an ordinary project directory.
    """
    try:
        entries = list(root.iterdir())
    except (PermissionError, OSError) as e:
        return f"cannot list {root}: {e}"

    names = {e.name for e in entries}
    hits = names & OS_ROOT_MARKERS
    if len(hits) >= 3:
        return f"root contains {len(hits)} OS-root-like dirs: {sorted(hits)}"

    if len(entries) >= SUSPICIOUS_TOPLEVEL_COUNT:
        return f"root has {len(entries)} top-level entries (>= {SUSPICIOUS_TOPLEVEL_COUNT}), unusual for a project"

    if root == Path(root.anchor):
        return f"root {root} is a filesystem anchor (drive/volume root)"

    return ""


def is_hidden(path: Path) -> bool:
    """Return True if the path's own name starts with a dot."""
    return path.name.startswith(".")


def should_skip_dir(path: Path, include_tests: bool) -> bool:
    """Return True if a directory should never be walked into."""
    if path.name in SKIP_DIRS:
        return True
    if is_hidden(path):
        return True
    return not include_tests and path.name.lower() in {"test", "tests"}


def is_test_file(path: Path) -> bool:
    """Return True if the file name marks it as test code."""
    stem = path.stem.lower()
    return stem.startswith("test_") or stem.endswith("_test") or stem == "conftest"


def first_doc_sentence(node) -> str:
    """Extract the first sentence of a docstring, regardless of line breaks.

    Splits on '.', '!', or '?' followed by whitespace/end-of-string, so a
    docstring written as one long paragraph still yields just the first
    sentence, not the whole block.
    """
    return first_sentence(ast.get_docstring(node, clean=True) or "")


def first_sentence(text: str) -> str:
    """Return the first sentence of text, with its whitespace collapsed."""
    text = " ".join(text.split())
    match = re.search(r"[.!?](\s|$)", text)
    if match:
        return text[: match.start() + 1]
    return text


def module_doc_sentence(tree: ast.Module) -> str:
    """Extract the first sentence of a module docstring, skipping any banner.

    Lines whose first non-blank character is `#` are a banner, not prose, so
    they go first. Then a one-line title paragraph with no sentence
    punctuation goes too, but only when another paragraph follows it.
    """
    doc = ast.get_docstring(tree, clean=True) or ""
    prose = "\n".join(
        line for line in doc.splitlines() if not line.lstrip().startswith("#")
    )
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
    if len(paragraphs) > 1:
        title = paragraphs[0]
        if "\n" not in title and not re.search(r"[.!?]", title):
            paragraphs = paragraphs[1:]
    return first_sentence(" ".join(paragraphs))


def format_args(args: ast.arguments) -> str:
    """Render a def's parameter names as a comma-separated signature string."""
    parts = []
    for a in args.posonlyargs:
        parts.append(a.arg)
    for a in args.args:
        parts.append(a.arg)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    for a in args.kwonlyargs:
        parts.append(a.arg)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    return ", ".join(parts)


def collect_defs(tree: ast.Module, include_private: bool):
    """Collect top-level and class-level function/class defs with their docstrings."""
    entries = []

    def visit(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            is_class = isinstance(child, ast.ClassDef)
            if not is_class and not isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            name = child.name
            if name.startswith("__") and name.endswith("__"):
                continue
            if name.startswith("_") and not include_private:
                continue
            qualname = f"{prefix}{name}"
            entry = {
                "name": qualname,
                "args": "" if is_class else format_args(child.args),
                "doc": first_doc_sentence(child),
                "line": child.lineno,
            }
            if is_class:
                entry["is_class"] = True
            entries.append(entry)
            if is_class:
                visit(child, prefix=f"{qualname}.")
            # Don't descend into function bodies for nested defs by default;
            # keeps the map flat and focused on the public-ish surface.

    visit(tree)
    return entries


def docstring_rows(tree: ast.Module) -> set:
    """Return the line numbers spanned by every docstring in the tree.

    Every docstring counts, nested and private included, since the line
    counts describe the file rather than the map.
    """
    rows = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        first = node.body[0]
        rows.update(range(first.lineno, first.end_lineno + 1))
    return rows


def count_lines(source: str, tree: ast.Module) -> dict:
    """Split a file's lines into code, blank, comments, and docstrings.

    Each line lands in exactly one column, the first that matches: code, then
    docstrings, then comments, then blank. So a trailing comment leaves its
    line as code, and so does a def and its docstring on one line. A token
    spanning several lines, such as a multi-line string, marks every line it
    spans. The line count is taken from the newlines, never `splitlines()`,
    which also splits on form feeds the tokenizer treats as ordinary.
    """
    total = source.count("\n") + (1 if source and not source.endswith("\n") else 0)
    doc_rows = docstring_rows(tree)
    code_rows = set()
    comment_rows = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        start, end = token.start[0], token.end[0]
        if token.type == tokenize.COMMENT:
            comment_rows.add(start)
        elif token.type == tokenize.STRING and start in doc_rows and end in doc_rows:
            continue  # the docstring itself, not code
        elif token.type not in LAYOUT_TOKENS:
            code_rows.update(range(start, end + 1))

    counts = dict.fromkeys(LINE_COLUMNS, 0)
    for row in range(1, total + 1):
        if row in code_rows:
            counts["code"] += 1
        elif row in doc_rows:
            counts["docstrings"] += 1
        elif row in comment_rows:
            counts["comments"] += 1
        else:
            counts["blank"] += 1
    return counts


def yaml_escape(s: str) -> str:
    """Minimal YAML-safe quoting for a scalar string value."""
    if s == "":
        return '""'
    needs_quote = any(c in s for c in ":#\"'{}[]&*!|>%@`") or s.strip() != s
    if needs_quote:
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def dump_yaml(files: dict) -> str:
    """Hand-rolled minimal YAML writer, no external deps required.

    Each file is a mapping of its module doc, its line counts, and its
    entries, the last omitted when empty. A `total:` mapping always closes
    the output, summed from the per-file counts.
    """
    out = []
    total = dict.fromkeys(LINE_COLUMNS, 0)
    for filepath in sorted(files):
        info = files[filepath]
        out.append(f"{filepath}:")
        out.append(f"  doc: {yaml_escape(info['doc'])}")
        out.append("  lines:")
        for column in LINE_COLUMNS:
            out.append(f"    {column}: {info['lines'][column]}")
            total[column] += info["lines"][column]
        if info["entries"]:
            out.append("  entries:")
        for d in info["entries"]:
            if d.get("is_class"):
                out.append(f"    - class: {yaml_escape(d['name'])}")
            else:
                sig = f"{d['name']}({d['args']})"
                out.append(f"    - def: {yaml_escape(sig)}")
            out.append(f"      doc: {yaml_escape(d['doc'])}")
            out.append(f"      line: {d['line']}")
    out.append("total:")
    out.append(f"  files: {len(files)}")
    for column in LINE_COLUMNS:
        out.append(f"  {column}: {total[column]}")
    return "\n".join(out) + "\n"


def walk_project(root: Path, include_private: bool, include_tests: bool):
    """Walk root for .py files, applying filters and the file ceiling.

    Returns a dict of relative path -> the file's module doc sentence,
    line counts, and collected def entries. Files that fail to parse,
    tokenize, or decode are skipped with a note to stderr, never fatally.
    Crossing the MAX_PY_FILES ceiling aborts the whole run -- it means the
    wrong root got passed in, and --force does not bypass this one.
    """
    files = {}
    py_count = 0
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if any(should_skip_dir(Path(p), include_tests) for p in rel_parts[:-1]):
            continue
        if is_hidden(path):
            continue
        if not include_tests and is_test_file(path):
            continue

        py_count += 1
        if py_count > MAX_PY_FILES:
            print(
                f"doc-map: found more than {MAX_PY_FILES} .py files under {root}, "
                f"this almost certainly isn't a single project. Aborting walk.",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            lines = count_lines(source, tree)
        except (SyntaxError, UnicodeDecodeError, tokenize.TokenError) as e:
            print(f"# skipped {path}: {e}", file=sys.stderr)
            continue

        files[str(path.relative_to(root))] = {
            "doc": module_doc_sentence(tree),
            "lines": lines,
            "entries": collect_defs(tree, include_private),
        }

    return files


DOC_MAP_HELP = "walk PATH and print the map to stdout"
DOC_MAP_USAGE = "doc-map print PATH [--include-private] [--include-tests] [--force]"
DOC_MAP_SLOTS = ("PATH",)

PRINT_PAGE = """\
        doc-map -- Print

https://github.com/east-van-ai/doc-map

Walk PATH and print its map to stdout as YAML. doc-map writes no files, so a
shell redirect is what puts a map on disk.

Each file gets a mapping. `doc` is the first sentence of its module
docstring, past any `#` banner. `lines` splits its lines into code, blank,
comments, and docstrings. `entries` lists every top-level and class-level
function and class, with the first sentence of its docstring and its line.
Methods carry dotted names like `Foo.bar`. A `total` closes the map.

The walk skips hidden, cache, build, and virtual environment directories,
test files and test directories, and single-underscore names. Dunder methods
are skipped always.

Two guardrails refuse a wrong root. A root that looks like an OS root is
refused unless `--force` is given. More than 5000 `.py` files aborts the
walk, and no flag lifts that."""
"""The prose of `print`'s page, standing in for a command module's docstring."""


def leading_paths(tokens):
    """Return the tokens ahead of the first flag."""
    paths = []
    for token in tokens:
        if token.startswith("-"):
            break
        paths.append(token)
    return paths


def usage_error(usage, message):
    """Report a command line doc-map could not read, with the matching usage."""
    sys.stdout.flush()
    print(f"doc-map: {message}", file=sys.stderr)
    print(f"Usage: {usage}", file=sys.stderr)
    return EXIT_ERROR


class ReadinessError(Exception):
    """A command line doc-map could read, naming a root it will not walk."""


def readiness_error(message):
    """Report what the run needed and did not find, with no usage line."""
    sys.stdout.flush()
    print(f"doc-map: {message}", file=sys.stderr)
    return EXIT_ERROR


def run_print(path, args):
    """Walk PATH and print the map, refusing a root that is not safe to walk."""
    root = Path(path).resolve()
    if not root.is_dir():
        raise ReadinessError(f"{root} is not a directory")

    if not args.force:
        reason = smells_like_system_root(root)
        if reason:
            raise ReadinessError(
                f"refusing to walk {root}: {reason}\n"
                "if you really mean it, rerun with --force"
            )

    files = walk_project(root, args.include_private, args.include_tests)
    sys.stdout.write(dump_yaml(files))


def installed_version():
    """Return the version of the installed doc-map distribution."""
    try:
        return metadata.version("doc-map")
    except metadata.PackageNotFoundError:
        return "unknown (not installed)"


def version_line():
    """Return the program name and the installed version on one line.

    Both spellings call this, so `doc-map version` and `doc-map --version`
    cannot drift apart.
    """
    return f"{PROG} {installed_version()}"


Command = namedtuple("Command", "bare usage slots action")
"""A command word's answer to being typed alone, its usage line, the path slots it
reads, and the action a full invocation runs.

`bare` returns the text for the bare word; `action` runs the command. For `version`,
both read from `version_line`, since running the command answers the bare word.
"""

COMMANDS = {
    "print": Command(
        lambda: command_page(PRINT_PAGE, add_print),
        DOC_MAP_USAGE,
        DOC_MAP_SLOTS,
        lambda paths, args: run_print(*paths, args),
    ),
    "version": Command(
        version_line,
        "doc-map version",
        (),
        lambda paths, args: print(version_line()),
    ),
}


def add_print(subparsers):
    """Add the `print` subparser and return it."""
    printer = subparsers.add_parser(
        "print", help=DOC_MAP_HELP, usage=DOC_MAP_USAGE, allow_abbrev=False
    )
    paths = printer.add_argument_group("paths")
    paths.add_argument("path", metavar="PATH", nargs="?", help="the directory to walk")
    printer.add_argument(
        "--include-private",
        action="store_true",
        help="include single-underscore names",
    )
    printer.add_argument(
        "--include-tests",
        action="store_true",
        help="include test files and test directories",
    )
    printer.add_argument(
        "--force",
        action="store_true",
        help="walk a root that failed the OS-root safety check",
    )
    return printer


def build_parser():
    """Construct the argument parser for the whole CLI.

    PATH is optional to argparse so that a bare command word reaches `main`
    and gets an answer instead of a usage error. Its parsed value goes
    unused: `main` reads the slot itself.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        **MONOCHROME,
        allow_abbrev=False,
        usage=f"{DOC_MAP_USAGE}\n       {COMMANDS['version'].usage}",
        epilog=PATHS,
        # Keeps the epilog's lines as written rather than joined into one paragraph.
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    add_print(subparsers)

    version_help = "print the installed version and exit"
    # Top-level only, so `doc-map print --version` stays an unknown flag.
    parser.add_argument(
        "--version", action="version", version=version_line(), help=version_help
    )
    # No arguments and no flags of its own, so a stray word after it is
    # doc-map's usage error rather than argparse's.
    subparsers.add_parser("version", help=version_help, allow_abbrev=False)
    return parser


def command_help(add_command):
    """Return one command's own `--help` text, as argparse prints it."""
    subparsers = argparse.ArgumentParser(prog=PROG, **MONOCHROME).add_subparsers()
    return add_command(subparsers).format_help()


def command_page(prose, add_command):
    """Return a command's answer to its bare word: its prose, then its --help.

    argparse documents the usage, the paths, and the flags, so each has one copy.
    """
    return f"{prose}\n\n{command_help(add_command).rstrip()}"


def main():
    """Parse arguments, run the matching command, return an exit code."""
    tokens = sys.argv[1:]

    if not tokens:
        print(f"{__doc__.strip()}\n\n{build_parser().format_help().rstrip()}")
        return EXIT_OK

    # A command word and nothing else is a question, and its own docs answer.
    if len(tokens) == 1 and tokens[0] in COMMANDS:
        print(COMMANDS[tokens[0]].bare())
        return EXIT_OK

    parser = build_parser()
    args, extras = parser.parse_known_args(tokens)

    if any(extra.startswith("-") for extra in extras):
        parser.parse_args(tokens)  # argparse names the flag better, exit 2

    # Not args.path: what argparse resolves from a token after a flag varies
    # by interpreter, and the grammar should not.
    paths = leading_paths(tokens[1:])

    command = COMMANDS[args.command]

    if len(paths) < len(command.slots):
        needed = " and ".join(command.slots)
        if len(command.slots) > 1:
            needed = f"both {needed}"
        return usage_error(command.usage, f"{args.command} needs {needed}")

    if len(paths) > len(command.slots):
        stray = paths[len(command.slots)]
        last = command.slots[-1] if command.slots else "it"
        return usage_error(
            command.usage,
            f"{args.command} takes nothing after {last}: {stray!r}",
        )

    try:
        command.action(paths, args)
    except ReadinessError as failure:
        return readiness_error(str(failure))

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
