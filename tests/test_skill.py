"""
Keep the agent skill's own shape: its frontmatter and its bytes.

Its commands run with every other doc's, in test_docs.py.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "doc-map" / "SKILL.md"


def test_frontmatter():
    """The file opens with `name: doc-map` and a description."""
    head = SKILL.read_text(encoding="utf-8").split("---\n")[1]
    assert "name: doc-map\n" in head
    assert re.search(r"description: \S", head)


def test_ascii():
    """The skill stays ASCII, like the rest of what a model is handed."""
    assert SKILL.read_bytes().isascii()
