"""
Keep the documents in step with the command line.

Every doc-map command a document shows runs through the real CLI, whether it
sits in a bash fence, a table row, or inline code. A table row states its exit
code in its last column. Every other command must exit 0, unless it matches a
row.
"""

import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# CHANGELOG.md is left out: it records commands that no longer exist.
DOCS = ["README.md", "docs/DESIGN.md", "skills/doc-map/SKILL.md"]

FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
SPAN = re.compile(r"`(doc-map(?: [^`]*)?)`")
ROW = "| `doc-map"
OPERATORS = {">", ">>", "|"}


def command_words(line):
    """Return the words after `doc-map` on a command line, or None for another program.

    Grammar brackets are stripped, so `[--force]` runs as `--force`. A leading
    `NAME=value` is dropped, `python3 -m doc_map.cli` reads as `doc-map`, and a
    shell operator ends the command, so a redirect runs as the map it redirects.
    """
    words = shlex.split(line.replace("[", "").replace("]", ""))
    while words and re.fullmatch(r"[A-Z_][A-Z0-9_]*=.*", words[0]):
        words.pop(0)
    for i, word in enumerate(words):
        if word in OPERATORS:
            words = words[:i]
            break
    if words[:1] == ["doc-map"]:
        return words[1:]
    if words[:3] == ["python3", "-m", "doc_map.cli"]:
        return words[3:]
    return None


def normalized(words):
    """Return the words as a lookup key, with `.` and `PATH` comparing equal."""
    return tuple("PATH" if word == "." else word for word in words)


def fence_commands(text):
    """Return each doc-map command in the text's bash fences, continuations joined."""
    commands = []
    for fence in FENCE.findall(text):
        for line in fence.replace("\\\n", " ").splitlines():
            words = command_words(line)
            if words is not None:
                commands.append(words)
    return commands


def table_rows(text):
    """Return the first and last cell of each table row that opens with a doc-map span."""
    rows = []
    for line in text.splitlines():
        if line.startswith(ROW):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append((cells[0], cells[-1]))
    return rows


def table_exits(text):
    """Return each literal table row's command, as a lookup key, mapped to its exit code."""
    exits = {}
    for first, last in table_rows(text):
        match = re.fullmatch(r"`(doc-map[^`]*)`", first)
        if match and last.isdigit():
            exits[normalized(command_words(match.group(1)))] = int(last)
    return exits


def inline_commands(text):
    """Return each doc-map command in inline code, outside bash fences and table rows.

    Spans are matched per paragraph, since a code span may wrap onto the next line.
    """
    lines = FENCE.sub("", text).splitlines()
    prose = "\n".join(line for line in lines if not line.startswith(ROW))
    commands = []
    for paragraph in re.split(r"\n\s*\n", prose):
        spans = SPAN.findall(paragraph.replace("\n", " "))
        commands.extend(command_words(span) for span in spans)
    return commands


def documented_commands():
    """Return every doc-map command the docs show, mapped to the exit code it must give."""
    texts = [(ROOT / doc).read_text(encoding="utf-8") for doc in DOCS]
    exits = {}
    for text in texts:
        exits.update(table_exits(text))
    expected = {}
    for text in texts:
        for words in fence_commands(text) + inline_commands(text):
            expected[tuple(words)] = exits.get(normalized(words), 0)
    expected.update(exits)
    return expected


# ---------- the docs against the real command line ----------


def test_every_command_exits_as_documented(run_cli, sample_project):
    """Each command gives its table row's exit code, or 0, with `PATH` filled in."""
    failures = []
    for words, code in documented_commands().items():
        argv = [str(sample_project) if word == "PATH" else word for word in words]
        result = run_cli(argv, cwd=ROOT)
        if result.returncode != code:
            command = " ".join(["doc-map", *words])
            failures.append(f"{command}: expected {code}, got {result.returncode}")
    assert failures == []


@pytest.mark.parametrize("doc", DOCS)
def test_every_doc_shows_a_command(doc):
    """A parser that silently finds nothing goes red."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert fence_commands(text) + inline_commands(text)


def test_table_rows_are_literal():
    """A row opening with a doc-map span is that span alone, ending in an exit code."""
    loose = []
    for doc in DOCS:
        for first, last in table_rows((ROOT / doc).read_text(encoding="utf-8")):
            if not (re.fullmatch(r"`doc-map[^`]*`", first) and last.isdigit()):
                loose.append(f"{doc}: {first}")
    assert loose == []


# ---------- the parser ----------


def test_grammar_brackets():
    """A grammar line runs with its brackets stripped."""
    text = "```bash\ndoc-map print PATH [--force]\n```\n"
    assert fence_commands(text) == [["print", "PATH", "--force"]]


def test_environment_prefix():
    """A leading `NAME=value` is dropped, and `python3 -m doc_map.cli` counts."""
    text = "```bash\nPYTHONPATH=src python3 -m doc_map.cli print PATH\n```\n"
    assert fence_commands(text) == [["print", "PATH"]]


def test_other_commands_skipped():
    """A line that runs something else, such as pipx, is not collected."""
    text = '```bash\npipx install "git+https://example.com/doc-map.git"\n```\n'
    assert fence_commands(text) == []


def test_shell_operator_ends_the_command():
    """A redirect runs as the map it redirects."""
    assert command_words("doc-map print . > map.yaml") == ["print", "."]


def test_table_row_states_its_exit():
    """A literal row maps its command to the code in its last column."""
    text = "| `doc-map print PATH extra` | usage error | 1 |\n"
    assert table_exits(text) == {("print", "PATH", "extra"): 1}


def test_dot_matches_a_path_row():
    """A prose `.` finds the row written with `PATH`."""
    exits = table_exits("| `doc-map print --force PATH` | usage error | 1 |\n")
    assert exits[normalized(["print", "--force", "."])] == 1


def test_inline_skips_what_is_not_a_command():
    """An error format like `doc-map: <message>` is not a command."""
    assert inline_commands("Errors read `doc-map: <message>`.\n") == []


def test_inline_span_wraps_onto_the_next_line():
    """A span broken by the prose wrap still counts, and never pairs across paragraphs."""
    text = "costs one token, `doc-map print\n.`, by name.\n\nA lone ` here.\n\n`x`\n"
    assert inline_commands(text) == [["print", "."]]


def test_inline_skips_fences_and_rows():
    """A command in a fence or a table row is not counted again as inline."""
    text = "```bash\n`doc-map print A`\n```\n| `doc-map print B` | x | 1 |\nSee `doc-map`.\n"
    assert inline_commands(text) == [[]]
