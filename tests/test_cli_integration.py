"""
CLI-level tests for docmap.cli.

These invoke `python -m docmap.cli` via subprocess to cover the CLI
grammar, guardrail refusals, and exit codes end to end.

The `run_cli` and `sample_project` fixtures live in conftest.py.
"""

from importlib import metadata

from docmap.cli import installed_version

# ---------- documentation ----------


def test_cli_bare_prints_banner(run_cli):
    result = run_cli([])
    assert result.returncode == 0
    assert "docmap print PATH" in result.stdout
    assert result.stderr == ""


def test_cli_bare_command_word_prints_the_same_banner(run_cli):
    bare = run_cli([])
    word = run_cli(["print"])
    assert word.returncode == 0
    assert word.stdout == bare.stdout


def test_cli_bare_with_piped_stdin_still_prints_banner(run_cli):
    result = run_cli([], input_text="")
    assert result.returncode == 0
    assert "docmap print PATH" in result.stdout


def test_cli_banner_advertises_neither_version_spelling(run_cli):
    result = run_cli([])
    assert "--version" not in result.stdout
    assert "docmap version" not in result.stdout


def test_cli_version_prints_name_and_number(run_cli):
    result = run_cli(["--version"])
    assert result.returncode == 0
    assert result.stdout.strip() == f"docmap {installed_version()}"
    assert result.stderr == ""


def test_cli_version_command_prints_name_and_number(run_cli):
    result = run_cli(["version"])
    assert result.returncode == 0
    assert result.stdout.strip() == f"docmap {installed_version()}"
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
    assert "Usage: docmap print" in result.stderr
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
    assert "Usage: docmap print PATH" in result.stderr


def test_cli_nonexistent_path_is_error(run_cli, tmp_path):
    result = run_cli(["print", str(tmp_path / "nope")])
    assert result.returncode == 1
    assert "is not a directory" in result.stderr
    assert result.stderr.startswith("docmap: ")


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
    assert "Usage: docmap version" in result.stderr
    assert "docmap print" not in result.stderr
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
    assert "docmap: refusing to walk" in result.stderr
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


# ---------- version ----------


def test_installed_version_reads_the_distribution_metadata():
    # Not pinned to pyproject's number: an editable install records the
    # version once, so a developer's tree lags behind an edit. A tree that
    # was never installed has no metadata at all.
    try:
        expected = metadata.version("docmap")
    except metadata.PackageNotFoundError:
        expected = "unknown (not installed)"
    assert installed_version() == expected


def test_installed_version_survives_a_missing_distribution(monkeypatch):
    def raise_not_found(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", raise_not_found)
    assert installed_version() == "unknown (not installed)"
