"""
CLI-level tests for doc_map.cli.

These invoke `python -m doc_map.cli` via subprocess to cover the CLI
grammar, guardrail refusals, and exit codes end to end.

The `run_cli` and `sample_project` fixtures live in conftest.py.
"""

from importlib import metadata

import pytest

from doc_map import cli
from doc_map.cli import (
    DOC_MAP_USAGE,
    add_print,
    build_parser,
    command_help,
    installed_version,
)

# ---------- documentation ----------


@pytest.fixture
def columns(monkeypatch):
    """Pin argparse's wrapping width, so in-process help matches the subprocess's."""
    monkeypatch.setenv("COLUMNS", "80")


def test_cli_bare_prints_banner(run_cli):
    result = run_cli([])
    assert result.returncode == 0
    assert "doc-map print PATH" in result.stdout
    assert result.stderr == ""


def test_cli_bare_ends_with_the_root_help(run_cli, columns):
    result = run_cli([])
    assert result.stdout.endswith(build_parser().format_help().rstrip() + "\n")


def test_cli_bare_print_is_its_own_page(run_cli, columns):
    result = run_cli(["print"])
    assert result.returncode == 0
    assert result.stdout.startswith("        doc-map -- Print\n")
    assert result.stdout.endswith(command_help(add_print).rstrip() + "\n")


def test_cli_print_help_starts_with_its_usage(run_cli):
    result = run_cli(["print", "--help"])
    assert result.returncode == 0
    assert result.stdout.startswith(f"usage: {DOC_MAP_USAGE}\n")


def test_cli_bare_with_piped_stdin_still_prints_banner(run_cli):
    result = run_cli([], input_text="")
    assert result.returncode == 0
    assert "doc-map print PATH" in result.stdout


def test_cli_help_lists_both_version_spellings_and_the_prose_neither(run_cli):
    result = run_cli([])
    assert "doc-map version" in result.stdout
    assert "--version" in result.stdout
    assert "version" not in cli.__doc__
    assert "version" not in cli.PRINT_PAGE


@pytest.mark.parametrize("words", [[], ["print"], ["--help"]])
def test_cli_help_prints_no_colour(run_cli, monkeypatch, words):
    monkeypatch.setenv("FORCE_COLOR", "1")
    result = run_cli(words)
    assert "\x1b" not in result.stdout


def test_cli_flags_do_not_abbreviate(run_cli, sample_project):
    result = run_cli(["print", str(sample_project), "--inc"])
    assert result.returncode == 2
    assert "unrecognized arguments: --inc" in result.stderr


def test_cli_version_prints_name_and_number(run_cli):
    result = run_cli(["--version"])
    assert result.returncode == 0
    assert result.stdout.strip() == f"doc-map {installed_version()}"
    assert result.stderr == ""


def test_cli_version_command_prints_name_and_number(run_cli):
    result = run_cli(["version"])
    assert result.returncode == 0
    assert result.stdout.strip() == f"doc-map {installed_version()}"
    assert result.stderr == ""


def test_cli_both_version_spellings_print_the_same_line(run_cli):
    # The two tests above would both pass with two copies of the line.
    # This is the one that fails if they drift.
    word = run_cli(["version"])
    flag = run_cli(["--version"])
    assert word.stdout == flag.stdout


# ---------- grammar ----------


def test_cli_print_without_path_is_usage_error(run_cli):
    result = run_cli(["print", "--include-private"])
    assert result.returncode == 1
    assert "print needs PATH" in result.stderr
    assert "Usage: doc-map print" in result.stderr
    assert result.stdout == ""


def test_cli_flags_follow_path_in_any_order(run_cli, sample_project):
    result = run_cli(["print", str(sample_project), "--force", "--include-private"])
    assert result.returncode == 0
    assert "mod.py:" in result.stdout


def test_cli_flag_before_path_is_usage_error(run_cli, sample_project):
    result = run_cli(["print", "--include-private", str(sample_project)])
    assert result.returncode == 1
    assert "print needs PATH" in result.stderr


def test_cli_second_positional_is_usage_error(run_cli, sample_project):
    result = run_cli(["print", str(sample_project), "extra"])
    assert result.returncode == 1
    assert "nothing after PATH" in result.stderr
    assert "Usage: doc-map print PATH" in result.stderr


def test_cli_nonexistent_path_is_error(run_cli, tmp_path):
    result = run_cli(["print", str(tmp_path / "nope")])
    assert result.returncode == 1
    assert "is not a directory" in result.stderr
    assert result.stderr.startswith("doc-map: ")


def test_cli_unknown_flag_is_argparse_error(run_cli, sample_project):
    result = run_cli(["print", str(sample_project), "--nope"])
    assert result.returncode == 2


def test_cli_version_on_the_command_is_argparse_error(run_cli, sample_project):
    result = run_cli(["print", str(sample_project), "--version"])
    assert result.returncode == 2
    assert "--version" in result.stderr
    assert result.stdout == ""


def test_cli_version_with_a_stray_word_is_usage_error(run_cli):
    result = run_cli(["version", "extra"])
    assert result.returncode == 1
    assert "version takes nothing after it" in result.stderr
    assert "'extra'" in result.stderr
    assert "Usage: doc-map version" in result.stderr
    assert "doc-map print" not in result.stderr
    assert result.stdout == ""


def test_cli_version_with_a_stray_flag_is_argparse_error(run_cli):
    result = run_cli(["version", "--nope"])
    assert result.returncode == 2
    assert result.stdout == ""


def test_cli_old_src_root_grammar_is_argparse_error(run_cli, sample_project):
    result = run_cli(["--src-root", str(sample_project)])
    assert result.returncode == 2


def test_cli_out_flag_is_gone(run_cli, sample_project):
    out_file = sample_project / "manifest.yaml"
    result = run_cli(["print", str(sample_project), "--out", str(out_file)])
    assert result.returncode == 2
    assert not out_file.exists()


# ---------- guardrails ----------


def test_cli_refuses_system_root_without_force(run_cli, tmp_path):
    for name in ("bin", "etc", "usr", "lib"):
        (tmp_path / name).mkdir()
    result = run_cli(["print", str(tmp_path)])
    assert result.returncode == 1
    assert "doc-map: refusing to walk" in result.stderr
    assert "--force" in result.stderr


def test_cli_force_overrides_system_root_sniff(run_cli, tmp_path):
    for name in ("bin", "etc", "usr", "lib"):
        (tmp_path / name).mkdir()
    result = run_cli(["print", str(tmp_path), "--force"])
    assert result.returncode == 0


# ---------- output ----------


def test_cli_prints_map_to_stdout(run_cli, sample_project):
    result = run_cli(["print", str(sample_project)])
    assert result.returncode == 0
    assert "mod.py:" in result.stdout
    assert "Say hello." in result.stdout


def test_cli_map_ends_with_a_total_that_matches_the_files(run_cli, sample_project):
    result = run_cli(["print", str(sample_project)])
    assert result.returncode == 0
    # sample_project's mod.py is three lines: a def, its docstring, a pass.
    assert result.stdout.endswith(
        "total:\n  files: 1\n  code: 2\n  blank: 0\n  comments: 0\n  docstrings: 1\n"
    )


def test_cli_maps_a_file_with_no_docstring_and_no_defs(run_cli, tmp_path):
    (tmp_path / "consts.py").write_text("X = 1\n")
    result = run_cli(["print", str(tmp_path)])
    assert result.returncode == 0
    assert result.stdout.startswith('consts.py:\n  doc: ""\n  lines:\n    code: 1\n')
    assert "entries:" not in result.stdout


# ---------- version ----------


def test_installed_version_reads_the_distribution_metadata():
    # Not pinned to pyproject's number: an editable install records the
    # version once, so a developer's tree lags behind an edit. A tree that
    # was never installed has no metadata at all.
    try:
        expected = metadata.version("doc-map")
    except metadata.PackageNotFoundError:
        expected = "unknown (not installed)"
    assert installed_version() == expected


def test_installed_version_survives_a_missing_distribution(monkeypatch):
    def raise_not_found(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", raise_not_found)
    assert installed_version() == "unknown (not installed)"
