"""perch brief: everything /walk reads for one project, as plain text.

Reads local files and Budgie in-process; never GitLab. Each section that
cannot be produced is one line saying why and what to run, and the rest
still prints. Team level only: no rate or cost per person.
"""

from __future__ import annotations

import json
from datetime import date

import yaml
from budgie.core.eac import at_completion
from budgie.core.montecarlo import simulate
from budgie.core.signals import evaluate

from perch.core import history
from perch.core.config import Config
from perch.core.doctor import age
from perch.core.money import load_money
from perch.core.steps import iso_week, people_lines, pull_fix, spec_path
from perch.core.trend import team_lines
from perch.core.workspace import Home

FOLLOWUP = "followup"
_ERRORS = (OSError, TypeError, ValueError, KeyError, yaml.YAMLError)
_ONLINE = "where GitLab is reachable"  # /walk itself never pulls


def _money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.0f}"


def _freshness(home: Home, name: str, config: Config, today: date):
    try:
        data = json.loads(config.board_dump.read_text())
        fetched = data.get("fetched_at") if isinstance(data, dict) else None
        yield f"board dump fetched {fetched or 'at an unknown time'}"
    except (OSError, ValueError):
        yield f"board dump: none; run perch fetch -p {name}"
    spec = None
    try:
        spec = spec_path(home, name, config)
    except ValueError as exc:
        yield str(exc)
    else:
        base = spec.with_name(spec.name + ".base")
        if base.exists():
            yield f"board YAML pulled {age(base)}"
        elif spec.exists():
            yield (
                f"board YAML has no .base (plan cannot diff it), last written "
                f"{age(spec)}; {pull_fix(name, spec)}"
            )
        else:
            yield f"board YAML: never pulled; {pull_fix(name, spec)}"
    try:
        last = max((r["week"] for r in history.load(config.history)), default=None)
    except _ERRORS as exc:
        yield f"last week recorded: history.jsonl unreadable: {exc}"
    else:
        yield f"last week recorded: {last or f'none; run perch board -p {name}'}"
    yield f"today: {iso_week(today)}"
    if spec:
        yield f"board file: {spec}"


def _forecast(config: Config):
    """Budgie's estimate at completion for the team, as `perch quarterly` runs it."""
    money = load_money(config.budgie_project)
    if money.as_of is None:
        yield "no hours booked yet: nothing to forecast from"
        return
    eac = at_completion(
        money.people, money.readings, money.span, as_of=money.as_of, plan=money.plan
    )
    sim = simulate(
        eac.people, iterations=money.iterations, seed=money.seed, costs=money.costs
    )
    budget = (
        money.budget_revisions.amount_on(money.span.last)
        if money.budget_revisions is not None
        else money.budget
    )
    line = (
        f"at completion P10 {_money(sim.percentile(10))}"
        f" · P50 {_money(sim.percentile(50))}"
        f" · P90 {_money(sim.percentile(90))}"
        f" · budget {_money(budget)}"
    )
    if budget is not None:
        signal = evaluate(sim, budget)
        line += f" · {signal.label} (over {signal.prob_over_budget:.0%})"
    yield line
    yield f"hours booked as of {money.as_of}; non-labor {_money(money.non_labor)}"


def _follow_ups(home: Home, name: str, config: Config):
    try:
        path = spec_path(home, name, config)
    except ValueError as exc:  # no gitlab_project: the fix, not a crash
        yield str(exc)
        return
    if not path.is_file():
        yield f"no board/{path.name}; run perch gb pull -p {name} {_ONLINE}"
        return
    spec = yaml.safe_load(path.read_text()) or {}
    if not isinstance(spec, dict):
        raise TypeError(f"{path.name} is not a board: its top level is not a mapping")
    columns = {c["name"] for c in spec.get("columns") or []}
    found = False
    for issue in spec.get("issues") or []:
        labels = issue.get("labels") or []
        if FOLLOWUP not in labels:
            continue
        found = True
        column = next((label for label in labels if label in columns), "Backlog")
        who = f"@{issue['assignee']}" if issue.get("assignee") else "unassigned"
        due = f"due {issue['due_date']}" if issue.get("due_date") else "no due date"
        iid = f"#{issue['iid']}" if issue.get("iid") else "new"
        yield f"{iid} · {issue['title']} · {column} · {who} · {due}"
    if not found:
        yield "none open"


def _under_section(text: str) -> list[str]:
    """The watch file's own headings two levels down, so they nest under ## Watch."""
    return ["##" + line if line.startswith("#") else line for line in text.splitlines()]


def build(home: Home, name: str, config: Config, today: date) -> list[str]:
    def rows():  # read per section: a corrupt line costs those sections, not all
        return history.load(config.history)

    week = iso_week(today)
    watch = home.watch_path(name, week)
    sections = {
        "Freshness": lambda: _freshness(home, name, config, today),
        "Team": lambda: team_lines(rows()),
        "People": lambda: people_lines(rows(), config.people) or ["no person rows yet"],
        "Forecast": lambda: _forecast(config),
        "Watch": lambda: (
            _under_section(watch.read_text())
            if watch.is_file()
            else [f"none for {week}; run perch monday -p {name}"]
        ),
        "Follow-ups": lambda: _follow_ups(home, name, config),
    }
    lines = [f"# perch brief: {name}"]
    for heading, make in sections.items():
        lines.append(f"## {heading}")
        try:
            lines.extend(make())
        except _ERRORS as exc:
            lines.append(f"{heading.lower()}: could not read: {exc}")
    return lines
