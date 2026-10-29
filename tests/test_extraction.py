"""
Unit tests for the AST/docstring/YAML layer of doc_map.cli:
first_doc_sentence, module_doc_sentence, format_args, collect_defs,
count_lines, yaml_escape, dump_yaml.
"""

import ast
from pathlib import Path

import pytest

from doc_map import cli
from doc_map.cli import (
    collect_defs,
    count_lines,
    dump_yaml,
    first_doc_sentence,
    format_args,
    module_doc_sentence,
    yaml_escape,
)


def _first_func_node(src: str):
    tree = ast.parse(src)
    return tree.body[0]


# ---------- first_doc_sentence ----------


def test_first_doc_sentence_simple():
    node = _first_func_node('def f():\n    """Do a thing."""\n    pass')
    assert first_doc_sentence(node) == "Do a thing."


def test_first_doc_sentence_multiline_paragraph():
    src = 'def f():\n    """Do a thing.\n\n    More detail here that should be dropped.\n    """\n    pass'
    node = _first_func_node(src)
    assert first_doc_sentence(node) == "Do a thing."


def test_first_doc_sentence_no_terminator():
    node = _first_func_node('def f():\n    """No terminator here"""\n    pass')
    assert first_doc_sentence(node) == "No terminator here"


def test_first_doc_sentence_missing():
    node = _first_func_node("def f():\n    pass")
    assert first_doc_sentence(node) == ""


def test_first_doc_sentence_question_mark():
    node = _first_func_node('def f():\n    """Is this it? Yes it is."""\n    pass')
    assert first_doc_sentence(node) == "Is this it?"


# ---------- format_args ----------


def test_format_args_all_kinds():
    src = "def f(a, b, /, c, *args, d, **kwargs): pass"
    node = _first_func_node(src)
    assert format_args(node.args) == "a, b, c, *args, d, **kwargs"


def test_format_args_empty():
    node = _first_func_node("def f(): pass")
    assert format_args(node.args) == ""


# ---------- yaml_escape ----------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", '""'),
        ("plain", "plain"),
        ("has: colon", '"has: colon"'),
        (" leading space", '" leading space"'),
        ('has "quote"', '"has \\"quote\\""'),
    ],
)
def test_yaml_escape(raw, expected):
    assert yaml_escape(raw) == expected


# ---------- collect_defs ----------


def test_collect_defs_skips_dunder_and_private_by_default():
    src = (
        "def public():\n    pass\n"
        "def _private():\n    pass\n"
        "def __dunder__():\n    pass\n"
    )
    tree = ast.parse(src)
    entries = collect_defs(tree, include_private=False)
    names = {e["name"] for e in entries}
    assert names == {"public"}


def test_collect_defs_include_private():
    src = "def _private():\n    pass\n"
    tree = ast.parse(src)
    entries = collect_defs(tree, include_private=True)
    assert {e["name"] for e in entries} == {"_private"}


def test_collect_defs_class_and_methods_qualified():
    src = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        pass\n"
        "    class Inner:\n"
        "        def baz(self):\n"
        "            pass\n"
    )
    tree = ast.parse(src)
    entries = collect_defs(tree, include_private=False)
    names = {e["name"] for e in entries}
    assert names == {"Foo", "Foo.bar", "Foo.Inner", "Foo.Inner.baz"}


def test_collect_defs_does_not_descend_into_function_bodies():
    src = "def outer():\n    def inner():\n        pass\n    return inner\n"
    tree = ast.parse(src)
    entries = collect_defs(tree, include_private=False)
    assert {e["name"] for e in entries} == {"outer"}


def test_collect_defs_skips_dunder_class_even_with_private():
    src = "class __Weird__:\n    pass\n"
    tree = ast.parse(src)
    entries = collect_defs(tree, include_private=True)
    assert entries == []


# ---------- dump_yaml ----------


def _file(entries, doc="", code=0, blank=0, comments=0, docstrings=0):
    return {
        "doc": doc,
        "lines": {
            "code": code,
            "blank": blank,
            "comments": comments,
            "docstrings": docstrings,
        },
        "entries": entries,
    }


def test_dump_yaml_file_shape_and_key_order():
    files = {
        "a.py": _file(
            [{"name": "f", "args": "x", "doc": "Do f.", "line": 4}],
            doc="Module a.",
            code=3,
            blank=1,
            comments=1,
            docstrings=2,
        )
    }
    assert dump_yaml(files) == (
        "a.py:\n"
        "  doc: Module a.\n"
        "  lines:\n"
        "    code: 3\n"
        "    blank: 1\n"
        "    comments: 1\n"
        "    docstrings: 2\n"
        "  entries:\n"
        "    - def: f(x)\n"
        "      doc: Do f.\n"
        "      line: 4\n"
        "total:\n"
        "  files: 1\n"
        "  code: 3\n"
        "  blank: 1\n"
        "  comments: 1\n"
        "  docstrings: 2\n"
    )


def test_dump_yaml_keeps_a_file_with_no_entries():
    out = dump_yaml({"empty.py": _file([])})
    assert 'empty.py:\n  doc: ""\n  lines:\n' in out
    assert "entries:" not in out


def test_dump_yaml_total_sums_every_file_and_comes_last():
    files = {"a.py": _file([], code=2, blank=1), "b.py": _file([], code=5)}
    out = dump_yaml(files)
    assert out.endswith(
        "total:\n  files: 2\n  code: 7\n  blank: 1\n  comments: 0\n  docstrings: 0\n"
    )


def test_dump_yaml_empty_map_still_has_a_total():
    assert dump_yaml({}).startswith("total:\n  files: 0\n")


def test_dump_yaml_class_marker():
    files = {
        "a.py": _file(
            [{"name": "Foo", "args": "", "doc": "", "line": 3, "is_class": True}]
        )
    }
    out = dump_yaml(files)
    assert "    - class: Foo" in out


# ---------- count_lines ----------


def _count(src: str):
    return count_lines(src, ast.parse(src))


EDGE_FILE = '''\
def f(): """One-liner."""
def g():
    """Doc."""  # trailing
    s = """not

a doc"""
    return s
'''


def test_count_lines_edge_file():
    assert _count(EDGE_FILE) == {
        "code": 6,
        "blank": 0,
        "comments": 0,
        "docstrings": 1,
    }


def test_count_lines_comment_and_blank_lines():
    src = '"""Mod."""\n\n# a comment\nx = 1  # trailing\n   \n'
    assert _count(src) == {"code": 1, "blank": 2, "comments": 1, "docstrings": 1}


def test_count_lines_multi_line_docstring_counts_every_line():
    src = 'class C:\n    """First.\n\n    More.\n    """\n'
    assert _count(src) == {"code": 1, "blank": 0, "comments": 0, "docstrings": 4}


def test_count_lines_counts_a_last_line_with_no_newline():
    assert _count("x = 1\ny = 2") == {
        "code": 2,
        "blank": 0,
        "comments": 0,
        "docstrings": 0,
    }


def test_count_lines_empty_file_is_all_zeros():
    assert _count("") == {"code": 0, "blank": 0, "comments": 0, "docstrings": 0}


@pytest.mark.parametrize(
    "src",
    [
        EDGE_FILE,
        '"""Mod."""\n\n# c\nx = (1,\n     2)\n',
        "x = 1 \\\n    + 2\n\f\ny = 3\n",
        "",
    ],
)
def test_count_lines_columns_sum_to_the_line_count(src):
    newlines = src.count("\n") + (1 if src and not src.endswith("\n") else 0)
    assert sum(_count(src).values()) == newlines


# ---------- module_doc_sentence ----------


def _module_doc(src: str):
    return module_doc_sentence(ast.parse(src))


def test_module_doc_sentence_plain_docstring():
    assert _module_doc('"""Walk a tree. Then more."""\n') == "Walk a tree."


def test_module_doc_sentence_skips_banner_and_title():
    src = (
        '"""\n'
        "# ======\n"
        "# East Van AI -- AI for the rest of us!\n"
        "# ======\n"
        "\n"
        "        weed-out\n"
        "\n"
        "weed-out deletes everything except what --keep lists. More here.\n"
        '"""\n'
    )
    assert _module_doc(src) == "weed-out deletes everything except what --keep lists."


def test_module_doc_sentence_all_banner_is_empty():
    assert _module_doc('"""\n# ======\n# East Van AI!\n# ======\n"""\n') == ""


def test_module_doc_sentence_keeps_a_lone_unpunctuated_line():
    assert _module_doc('"""Utilities"""\n') == "Utilities"


def test_module_doc_sentence_no_docstring_is_empty():
    assert _module_doc("x = 1\n") == ""


def test_module_doc_sentence_reads_doc_maps_own_banner():
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert module_doc_sentence(ast.parse(source)).startswith("doc-map walks a Python")
