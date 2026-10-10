from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REL = ".github/ISSUE_TEMPLATE/task.md"


def test_issue_template_has_fields_in_order():
    text = (ROOT / REL).read_text()
    pos = [text.index(f) for f in ("Goal:", "Done when:", "Context:", "Out of scope:", "Links:")]
    assert pos == sorted(pos)


@pytest.mark.parametrize("app", ["remote-gitboard", "budgie"])
def test_issue_template_copies_match(app):
    copy = ROOT / "apps" / app / REL
    if not copy.exists():
        pytest.skip(f"apps/{app} has no template yet")
    assert copy.read_text() == (ROOT / REL).read_text()
