"""
Keep the agent skill in step with the command line.
"""

import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "doc-map" / "SKILL.md"


def skill_commands(text):
    """Return each doc-map command in the skill's bash fences, continuations joined.

    A leading `NAME=value` is dropped, `python3 -m doc_map.cli` reads as
    `doc-map`, and grammar brackets are stripped, so `[--force]` runs as
    `--force`.
    """
    commands = []
    for fence in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        for line in fence.replace("\\\n", " ").splitlines():
            words = shlex.split(line.replace("[", "").replace("]", ""))
            while words and re.fullmatch(r"[A-Z_][A-Z0-9_]*=.*", words[0]):
                words.pop(0)
            if words[:1] == ["doc-map"]:
                commands.append(words[1:])
            elif words[:3] == ["python3", "-m", "doc_map.cli"]:
                commands.append(words[3:])
    return commands


def test_every_command_runs(run_cli, sample_project):
    """Each command exits 0, with `PATH` filled in by a sample project."""
    commands = skill_commands(SKILL.read_text(encoding="utf-8"))
    assert {argv[0] for argv in commands} == {"print"}
    for argv in commands:
        argv = [str(sample_project) if word == "PATH" else word for word in argv]
        result = run_cli(argv, cwd=ROOT)
        assert result.returncode == 0, (argv, result.stderr)


def test_frontmatter():
    """The file opens with `name: doc-map` and a description."""
    head = SKILL.read_text(encoding="utf-8").split("---\n")[1]
    assert "name: doc-map\n" in head
    assert re.search(r"description: \S", head)


def test_ascii():
    """The skill stays ASCII, like the rest of what a model is handed."""
    assert SKILL.read_bytes().isascii()


def test_grammar_brackets():
    """A grammar line runs with its brackets stripped."""
    text = "```bash\ndoc-map print PATH [--force]\n```\n"
    assert skill_commands(text) == [["print", "PATH", "--force"]]


def test_environment_prefix():
    """A leading `NAME=value` is dropped, and `python3 -m doc_map.cli` counts."""
    text = "```bash\nPYTHONPATH=src python3 -m doc_map.cli print PATH\n```\n"
    assert skill_commands(text) == [["print", "PATH"]]


def test_other_commands_skipped():
    """A line that runs something else, such as pipx, is not collected."""
    text = '```bash\npipx install "git+https://example.com/doc-map.git"\n```\n'
    assert skill_commands(text) == []
