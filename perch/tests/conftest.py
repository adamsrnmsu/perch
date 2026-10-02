"""One small, hand-checkable world shared by the tests.

2026, no PTO, so a full-time year is 1,992 hours.

  Alice ($100/h, 0.5 FTE = 996 h)  readings wk4=40 wk8=100 wk12=160 wk16=200
      closed 2, 2, 3, 1 issues in those four intervals -> 20, 30, 20, 40 h/issue
      own rate: low 20, mode 200/8 = 25, high 40
  Bob   ($50/h, 0.5 FTE = 996 h)   readings wk8=80 wk16=120
      closed 4, 1 -> two samples, so no spread: 120/5 = 24
  Team rate 320/13 = 24.6

Open: Alice #101 (estimated 10 h, 8-14), #102, #103; Bob #104, #105;
#104 is Blocked since 2026-04-06 (14 days at the 04-20 fetch);
#105 has an unanswered "Q: which env?";
#106 unassigned; #107 assigned to cdoe, who is not in perch.yaml.

Board moves for the quarterly report: #102 sat in Blocked 2026-04-02 to 04-07
(5 days); #8 went into Done 04-08 and back out 04-09 before closing on 04-10.
The dump keeps 90 days, so it covers 2026-01-20 to the 04-20 fetch.
"""

import json
import os
from datetime import date

import pytest

# Colour off before rich loads: CLI tests assert on rendered text, and an
# exported FORCE_COLOR splits it with ANSI codes.
os.environ.pop("FORCE_COLOR", None)


def week(number: int) -> date:
    return date.fromisocalendar(2026, number, 7)


def issue(iid, assignee=None, closed=None, labels=(), transitions=(), questions=()):
    rec = {
        "iid": iid,
        "title": f"Issue {iid}",
        "state": "closed" if closed else "opened",
        "assignee": assignee,
        "labels": list(labels),
        "closed_at": f"{closed}T12:00:00.000Z" if closed else None,
        "transitions": list(transitions),
    }
    if questions:  # gitboard's `questions`; older dumps have no such key
        rec["questions"] = [
            {"ts": "2026-04-15T09:00:00.000Z", "author": "x", "text": q}
            for q in questions
        ]
    return rec


def history():
    closed = (
        [("asmith", "2026-01-10")] * 2
        + [("asmith", "2026-02-10")] * 2
        + [("asmith", "2026-03-10")] * 3
        + [("asmith", "2026-04-10")]
        + [("bjones", "2026-02-01")] * 4
        + [("bjones", "2026-04-01")]
    )
    records = [
        issue(n, who, day, ["epic::billing"] if n <= 4 else [])
        for n, (who, day) in enumerate(closed, start=1)
    ]
    records[7]["transitions"] = [  # #8: into Done, back out, then closed
        ["2026-04-08T09:00:00.000Z", "add", "Done"],
        ["2026-04-09T09:00:00.000Z", "remove", "Done"],
    ]
    records += [
        issue(101, "asmith", labels=["epic::billing"]),
        issue(
            102,
            "asmith",
            transitions=[
                ["2026-04-02T09:00:00.000Z", "add", "Blocked"],
                ["2026-04-07T09:00:00.000Z", "remove", "Blocked"],
            ],
        ),
        issue(103, "asmith"),
        issue(
            104,
            "bjones",
            labels=["Blocked"],
            transitions=[["2026-04-06T09:00:00.000Z", "add", "Blocked"]],
        ),
        issue(105, "bjones", questions=["Q: which env?"]),
        issue(106),
        issue(107, "cdoe"),
    ]
    return records


def build_world(tmp_path):
    """A Budgie project, a gitboard dump, estimates and a perch.yaml on disk.

    A plain function as well as a fixture, so the same world can be built by
    hand to look at the CLI's real output.
    """
    project = tmp_path / "fy26"
    project.mkdir()
    (project / "budgie.yaml").write_text("year: 2026\nbudget: 100000\nseed: 1\n")
    (project / "people.csv").write_text(
        "name,hourly_cost,hours_low,hours_mode,hours_high\n"
        "Alice,100,900,1000,1100\nBob,50,900,1000,1100\n"
    )
    (project / "allocations.csv").write_text(
        "name,fte,hours_spent\nAlice,0.5,0\nBob,0.5,0\n"
    )
    (project / "weekly.csv").write_text(
        "name,week,hours_to_date\n"
        "Alice,4,40\nAlice,8,100\nAlice,12,160\nAlice,16,200\nBob,8,80\nBob,16,120\n"
    )
    (project / "costs.csv").write_text(
        "name,category,date,amount,low,high,recurring\n"
        "Laptops,materials,2026-03-15,5000,,,no\n"
    )
    (tmp_path / "dump.json").write_text(
        json.dumps(
            {
                "project": "grp/proj",
                "board": "Dev",
                "columns": ["Doing", "Done"],
                "fetched_at": "2026-04-20T08:00:00+00:00",
                "history": history(),
            }
        )
    )
    (tmp_path / "estimates.csv").write_text(
        "key,hours,low,high\n#101,10,8,14\n#1,15,,\n#2,15,,\nepic::billing,60,50,80\n"
    )
    config = tmp_path / "perch.yaml"
    config.write_text(
        "budgie_project: fy26\nboard_dump: dump.json\nestimates: estimates.csv\n"
        "people:\n  asmith: Alice\n  bjones: Bob\n"
    )
    return config


def since(world, day):
    """Give the world's dump gitboard's `since`: where its history starts."""
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    meta["since"] = f"{day}T08:00:00+00:00"
    dump.write_text(json.dumps(meta))


@pytest.fixture
def world(tmp_path):
    return build_world(tmp_path)


@pytest.fixture(autouse=True)
def _no_perch_home(monkeypatch):
    """A PERCH_HOME in the developer's shell must not find a real workspace."""
    monkeypatch.delenv("PERCH_HOME", raising=False)


def build_home(tmp_path, *names, gitlab=True):
    """A workspace whose projects are each the hand-checkable world above.

    Each project's Budgie project is its own `fy26/` (perch.yaml points there),
    so every number the world's docstring works out holds per project.
    """
    from perch.core.workspace import create_home

    home = create_home(tmp_path / "ws", tmp_path / "gb")
    for name in names:
        folder = home.projects_dir / name
        folder.mkdir(parents=True)
        config = build_world(folder)
        if gitlab:
            config.write_text(config.read_text() + f"gitlab_project: grp/{name}\n")
    return home


@pytest.fixture
def quarter_world(world):
    """The world above, plus the dated money files a quarterly report reads.

    budget.csv (the pin in budgie.yaml is dropped, since a pin beats it):
    $100,000 from Jan 1, $120,000 from 2026-04-15 ("Q2 increase").
    plan.csv: Alice and Bob at 0.5 from Jan 1; Bob down to 0.25 from 2026-05-01.
    2026 has 250 working days, so a day is 1,992 / 250 = 7.968 h; 167 are left
    from May 1, so the change takes 167 x 7.968 x 0.25 = 332.664 h off Bob's
    year: $16,633.20 at $50.
    """
    project = world.parent / "fy26"
    (project / "budgie.yaml").write_text("year: 2026\nseed: 1\n")
    (project / "budget.csv").write_text(
        "effective_date,amount,note\n"
        "2026-01-01,100000,Original\n2026-04-15,120000,Q2 increase\n"
    )
    (project / "plan.csv").write_text(
        "name,effective_date,fte\n"
        "Alice,2026-01-01,0.5\nBob,2026-01-01,0.5\nBob,2026-05-01,0.25\n"
    )
    return world
