import pytest

from perch.core.config import load_config


def test_paths_resolve_against_the_config_file(world):
    config = load_config(world)
    assert config.budgie_project == world.parent / "fy26"
    assert config.board_dump == world.parent / "dump.json"
    assert config.estimates == world.parent / "estimates.csv"
    assert config.people == {"asmith": "Alice", "bjones": "Bob"}
    assert config.history == world.parent / "history.jsonl"


def test_estimates_are_optional(world):
    world.write_text("budgie_project: fy26\nboard_dump: dump.json\n")
    assert load_config(world).estimates is None


@pytest.mark.parametrize(
    ("text", "error", "says"),
    [
        ("board_dump: dump.json\n", ValueError, "`budgie_project` is required"),
        ("budgie_project: nope\nboard_dump: dump.json\n", FileNotFoundError, "budgie.yaml"),
        ("budgie_project: fy26\nboard_dump: nope.json\n", FileNotFoundError, "stats --dump"),
        ("budgie_project: fy26\nboard_dump: dump.json\nestimates: nope.csv\n", FileNotFoundError, "`estimates`"),
        ("budgie_project: fy26\nboard_dump: dump.json\npeeple: {}\n", ValueError, "peeple"),
    ],
)  # fmt: skip
def test_a_bad_config_names_the_key_at_fault(world, text, error, says):
    world.write_text(text)
    with pytest.raises(error, match=says):
        load_config(world)


def test_a_missing_config_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match="perch.yaml"):
        load_config(tmp_path / "perch.yaml")
