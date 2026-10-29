"""
Unit tests for the filter/guardrail/walk layer of doc_map.cli:
is_test_file, should_skip_dir, smells_like_system_root, walk_project.
"""

from pathlib import Path

import pytest

from doc_map import cli
from doc_map.cli import (
    is_test_file,
    should_skip_dir,
    smells_like_system_root,
    walk_project,
)

# ---------- is_test_file / should_skip_dir ----------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("test_foo.py", True),
        ("foo_test.py", True),
        ("conftest.py", True),
        ("foo.py", False),
        ("testing_utils.py", False),
    ],
)
def test_is_test_file(name, expected):
    assert is_test_file(Path(name)) is expected


def test_should_skip_dir_known_dirs():
    assert should_skip_dir(Path("__pycache__"), include_tests=True)
    assert should_skip_dir(Path(".git"), include_tests=True)
    assert not should_skip_dir(Path("src"), include_tests=True)


def test_should_skip_dir_allows_ordinary_package_names():
    """`data` is a real package name, not build output."""
    assert not should_skip_dir(Path("data"), include_tests=True)


def test_should_skip_dir_tests_flag():
    assert should_skip_dir(Path("tests"), include_tests=False)
    assert not should_skip_dir(Path("tests"), include_tests=True)


def test_should_skip_dir_hidden():
    assert should_skip_dir(Path(".hidden"), include_tests=True)


# ---------- smells_like_system_root ----------


def test_smells_like_system_root_ordinary_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hi")
    assert smells_like_system_root(tmp_path) == ""


def test_smells_like_system_root_os_markers(tmp_path):
    for name in ("bin", "etc", "usr", "lib"):
        (tmp_path / name).mkdir()
    reason = smells_like_system_root(tmp_path)
    assert reason != ""
    assert "OS-root-like" in reason


def test_smells_like_system_root_too_many_entries(tmp_path):
    for i in range(35):
        (tmp_path / f"dir{i}").mkdir()
    reason = smells_like_system_root(tmp_path)
    assert "top-level entries" in reason


# ---------- walk_project ----------


def test_walk_project_basic(tmp_path):
    (tmp_path / "mod.py").write_text('def hello():\n    """Say hello."""\n    pass\n')
    (tmp_path / "test_mod.py").write_text("def test_hello():\n    pass\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "junk.py").write_text("def junk(): pass\n")

    entries = walk_project(tmp_path, include_private=False, include_tests=False)

    assert "mod.py" in entries
    assert "test_mod.py" not in entries
    assert not any("__pycache__" in k for k in entries)
    assert entries["mod.py"]["entries"][0]["doc"] == "Say hello."


def test_walk_project_maps_module_doc_and_line_counts(tmp_path):
    (tmp_path / "mod.py").write_text('"""A module."""\n\n# note\nX = 1\n')

    entries = walk_project(tmp_path, include_private=False, include_tests=False)

    assert entries["mod.py"] == {
        "doc": "A module.",
        "lines": {"code": 1, "blank": 1, "comments": 1, "docstrings": 1},
        "entries": [],
    }


def test_walk_project_walks_a_data_package(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "loader.py").write_text(
        'def load():\n    """Load a fixture."""\n    pass\n'
    )

    entries = walk_project(tmp_path, include_private=False, include_tests=False)

    assert "data/loader.py" in entries
    assert entries["data/loader.py"]["entries"][0]["doc"] == "Load a fixture."


def test_walk_project_include_tests(tmp_path):
    (tmp_path / "test_mod.py").write_text("def test_hello():\n    pass\n")
    entries = walk_project(tmp_path, include_private=False, include_tests=True)
    assert "test_mod.py" in entries


def test_walk_project_skips_unparseable_file(tmp_path, capsys):
    (tmp_path / "broken.py").write_text("def f(:\n    pass\n")
    (tmp_path / "ok.py").write_text("def g():\n    pass\n")
    entries = walk_project(tmp_path, include_private=False, include_tests=False)
    assert "broken.py" not in entries
    assert "ok.py" in entries


def test_walk_project_max_py_files_ceiling(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "MAX_PY_FILES", 2)
    for i in range(5):
        (tmp_path / f"m{i}.py").write_text("def f(): pass\n")
    with pytest.raises(SystemExit) as exc_info:
        walk_project(tmp_path, include_private=False, include_tests=False)
    assert exc_info.value.code == 1
