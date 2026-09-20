"""One small, hand-checkable world shared by the tests.

2026, no PTO, so a full-time year is 1,992 hours.

  Alice ($100/h, 0.5 FTE = 996 h)  readings wk4=40 wk8=100 wk12=160 wk16=200
      closed 2, 2, 3, 1 issues in those four intervals -> 20, 30, 20, 40 h/issue
      own rate: low 20, mode 200/8 = 25, high 40
  Bob   ($50/h, 0.5 FTE = 996 h)   readings wk8=80 wk16=120
      closed 4, 1 -> two samples, so no spread: 120/5 = 24
  Team rate 320/13 = 24.6

Open: Alice #101 (estimated 10 h, 8-14), #102, #103; Bob #104, #105;
#106 unassigned; #107 assigned to cdoe, who is not in perch.yaml.
"""

import json
from datetime import date

import pytest


def week(number: int) -> date:
    return date.fromisocalendar(2026, number, 7)


def issue(iid, assignee=None, closed=None, labels=()):
    return {
        "iid": iid,
        "title": f"Issue {iid}",
        "state": "closed" if closed else "opened",
        "assignee": assignee,
        "labels": list(labels),
        "closed_at": f"{closed}T12:00:00.000Z" if closed else None,
        "transitions": [],
    }


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
    records += [
        issue(101, "asmith", labels=["epic::billing"]),
        issue(102, "asmith"),
        issue(103, "asmith"),
        issue(104, "bjones"),
        issue(105, "bjones"),
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


@pytest.fixture
def world(tmp_path):
    return build_world(tmp_path)
