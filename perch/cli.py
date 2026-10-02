"""The perch command line: a thin adapter over perch.core."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from perch.core.steps import MONDAY_STEPS

console = Console()

_SIGNAL_STYLE = {"GREEN": "green", "YELLOW": "yellow", "RED": "red", "BLUE": "blue"}


def _hours(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.0f}"


def _spread(low: float, mode: float, high: float) -> str:
    """`60 (48–94)`, or just `48` when there is no spread to show."""
    if round(low) == round(high):
        return _hours(mode)
    return f"{_hours(mode)} ({_hours(low)}–{_hours(high)})"


def _rate(value: float) -> str:
    """Rates to the nearest half hour: the inputs are not finer than that."""
    return f"{round(value * 2) / 2:g}"


def _load(config_path: Path):
    from perch.core.board import load_board
    from perch.core.config import load_config
    from perch.core.estimates import load_estimates
    from perch.core.join import calibrate
    from perch.core.money import load_money

    config = load_config(config_path)
    board = load_board(config.board_dump)
    money = load_money(config.budgie_project)
    estimates = load_estimates(config.estimates) if config.estimates else {}
    rates = calibrate(money.readings, board, config.people, money.year)
    return config, board, money, estimates, rates


_config_option = click.option(
    "--config",
    "config_path",
    default=None,
    help="A perch.yaml to use instead of a workspace project.",
)
_project_option = click.option(
    "-p",
    "--project",
    default=None,
    help="Which project under projects/ (needed when there are several).",
)


def _bin_dir() -> Path:
    """perch's venv: `perch` and `budgie` (installed there) sit beside python."""
    return Path(sys.executable).parent


def _find_home():
    from perch.core.workspace import find_home

    return find_home(Path.cwd(), os.environ)


def _home():
    from perch.core.workspace import WorkspaceError

    try:
        return _find_home()
    except WorkspaceError as exc:
        raise click.ClickException(str(exc)) from exc


def _config_path(config_path: str | None, project: str | None) -> Path:
    """--config, then -p, then ./perch.yaml, then the workspace's project.

    A perch.yaml in this directory beats $PERCH_HOME: it is the one you are
    standing next to. In the workspace, the project folder you are in counts.
    """
    from perch.core.config import CONFIG_NAME

    if config_path:
        return Path(config_path)
    if project is None and Path(CONFIG_NAME).is_file():
        return Path(CONFIG_NAME)
    home = _find_home()
    return home.config_path(home.select(project, Path.cwd()))


def _run(step) -> None:
    """Run one step in this terminal; the tool's own output shows as it happens."""
    from perch.core.steps import StepFailed

    for directory in step.makes:
        directory.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold]{escape(step.name)}[/bold] [dim]{escape(step.shown())}[/dim]")
    code = subprocess.run(
        step.argv, cwd=step.cwd, env={**os.environ, **step.env}, check=False
    ).returncode
    if code:
        raise StepFailed(step, code)


# --help in the order the work goes, not alphabetical. Every command is in one.
_SECTIONS = {
    "Set up": ["init", "projects", "doctor"],
    "Every Monday, in order": [
        "status",
        "hours",
        "fetch",
        "board",
        "weekly",
        "digest",
        "emails",
        "monday",
    ],
    "Look closer": [
        "accuracy",
        "budget",
        "forecast",
        "cut",
        "watch",
        "quarterly",
        "tui",
    ],
}


class _SectionedGroup(click.Group):
    def format_commands(self, ctx, formatter):
        limit = formatter.width - 6 - max(len(name) for name in self.commands)
        for title, names in _SECTIONS.items():
            rows = [(n, self.commands[n].get_short_help_str(limit)) for n in names]
            with formatter.section(title):
                formatter.write_dl(rows)


@click.group(cls=_SectionedGroup)
def cli():
    """perch -- what the open board means for the budget."""


@cli.command()
@_config_option
@_project_option
@click.option("--seed", default=None, type=int, help="Seed the simulation.")
@click.option("--iterations", default=None, type=int, help="Simulation draws.")
@click.option("--no-history", is_flag=True, help="Don't append to history.jsonl.")
def board(config_path, project, seed, iterations, no_history):
    """Step 2: cost to clear the open board, against the hours and budget left."""
    from perch.core.accuracy import by_person
    from perch.core.history import record, rows_for
    from perch.core.join import notes, person_rows, rollup

    try:
        config, the_board, money, estimates, rates = _load(
            _config_path(config_path, project)
        )
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    rows = person_rows(the_board, estimates, rates, config.people, money)
    summary = rollup(rows, money, iterations=iterations, seed=seed)

    table = Table(title=f"{the_board.project} — {the_board.name}: the open board")
    for head in ("Name", "Open", "Hours", "Cost", "Left", "Gap", "Basis"):
        table.add_column(head, justify="left" if head in ("Name", "Basis") else "right")
    for r in rows:
        gap = _hours(r.gap)
        if r.gap is not None and r.gap < 0:
            gap = f"[bold red]{gap}[/bold red]"
        table.add_row(
            r.name,
            str(r.open),
            _spread(r.low, r.mode, r.high),
            _money(r.cost),
            _hours(r.left),
            gap,
            ", ".join(r.bases) or "no basis",
        )
    console.print(table)
    _print_rates(rates)

    when = f"as of {summary.as_of}" if summary.as_of else "no hours readings"
    console.print(f"Spent to date             {_money(summary.spent_cost)}   ({when})")
    console.print(
        f"Cost to clear the board   {_money(summary.clear_p50)}   "
        f"(P10 {_money(summary.clear_p10)} – P90 {_money(summary.clear_p90)})"
    )
    console.print(f"Planned non-labor         {_money(summary.non_labor)}")
    if summary.budget is not None:
        console.print(f"Budget (latest)           {_money(summary.budget)}")
        console.print(f"Headroom after the board  {_money(summary.headroom)}")
    if summary.signal is not None:
        style = _SIGNAL_STYLE[summary.signal.signal.name]
        console.print(
            f"[{style}]●[/{style}] {summary.signal.label.upper()} — "
            f"{summary.signal.prob_over_budget:.0%} chance the board alone "
            "breaks the budget that is left"
        )
    console.print(
        "[dim]Not a year forecast: a board rarely holds the rest of the year's "
        "work. `budgie forecast` says where the plan lands.[/dim]"
    )
    for note in notes(the_board, rows, config.people, money):
        console.print(f"[yellow]![/yellow] {note}")

    if not no_history:
        accuracy = by_person(estimates, the_board, config.people, money)
        record(
            config.history,
            the_board.fetched_on,
            rows_for(
                rows,
                rates,
                summary,
                accuracy if estimates else (),
                left=sum(money.left.values()),
            ),
        )


def _print_rates(rates):
    if rates.types is None:
        console.print(
            "[dim]Type rates: not enough history to fit yet "
            "(needs more reading intervals than issue types + 2).[/dim]"
        )
        return
    table = Table(
        title=f"Hours per issue by type — modelled, {rates.types.intervals} intervals"
    )
    table.add_column("Who")
    columns = sorted(rates.types.rates)
    for column in columns:
        table.add_column(column, justify="right")
    table.add_row("team", *(_rate(rates.types.rates[c]) for c in columns))
    for name, factor in sorted(rates.types.factors.items()):
        table.add_row(name, *(_rate(factor * rates.types.rates[c]) for c in columns))
    console.print(table)
    console.print(
        "[dim]Modelled, not measured: each person's pace is assumed the same "
        "across types, so this cannot show someone quick on one type and slow "
        "on another.[/dim]"
    )


@cli.command()
@_config_option
@_project_option
def accuracy(config_path, project):
    """How estimates compared with what the work took."""
    from perch.core.accuracy import by_label, by_person

    try:
        config, the_board, money, estimates, rates = _load(
            _config_path(config_path, project)
        )
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    if not estimates:
        raise click.ClickException(
            "No `estimates:` file in perch.yaml, so there is nothing to compare."
        )

    labels = Table(title="By label — estimated vs MODELLED hours")
    for head in ("Label", "Issues", "Open", "Estimated", "Modelled", "Ratio", "$"):
        labels.add_column(head, justify="left" if head == "Label" else "right")
    for a in by_label(estimates, the_board, rates, config.people, money):
        ratio = "—" if a.ratio is None else f"{a.ratio:.2f}x"
        labels.add_row(
            a.label,
            str(a.issues),
            str(a.open),
            _hours(a.estimated),
            _hours(a.modelled),
            ratio,
            f"{a.dollars:+,.0f}",
        )
    console.print(labels)

    persons = Table(title="By person — booked vs estimated hours (measured)")
    for head in ("Name", "Closed", "With estimate", "Booked", "Estimated", "Ratio"):
        persons.add_column(head, justify="left" if head == "Name" else "right")
    for p in by_person(estimates, the_board, config.people, money):
        ratio = f"{p.ratio:.2f}x" if p.ratio is not None else "too few estimates"
        persons.add_row(
            p.name,
            str(p.closed),
            f"{p.covered} ({p.coverage:.0%})",
            _hours(p.booked),
            _hours(p.estimated),
            ratio,
        )
    console.print(persons)
    console.print(
        "[dim]Ratio is booked hours, scaled to the share of issues that had an "
        "estimate, over those estimates. Below 50% coverage no ratio is shown. "
        "Compare a person with their own earlier weeks, never with each other.[/dim]"
    )


@cli.command()
@_config_option
@_project_option
@click.option("--person", default=None, help="Only this person (a name in `people:`).")
@click.option("--out", "out_path", default=None, help="Write the markdown here.")
def weekly(config_path, project, person, out_path):
    """Step 3: per-person markdown drafts for the weekly digest. Nothing is sent."""
    from perch.core.accuracy import by_person
    from perch.core.history import load
    from perch.core.join import person_rows
    from perch.core.weekly import weekly as render

    try:
        config, the_board, money, estimates, rates = _load(
            _config_path(config_path, project)
        )
        rows = person_rows(the_board, estimates, rates, config.people, money)
        text = render(
            the_board,
            money,
            rates,
            rows,
            by_person(estimates, the_board, config.people, money),
            bool(estimates),
            config.people,
            load(config.history),
            only=person,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    if out_path:
        Path(out_path).write_text(text)
        console.print(f"Wrote {out_path}")
    else:
        click.echo(text, nl=False)


@cli.command()
def projects():
    """The projects in this workspace and how fresh each one's data is."""
    from perch.core.config import load_config
    from perch.core.doctor import age

    home = _home()
    names = home.projects()
    if not names:
        console.print("No projects yet. Run: perch init <name>")
        return
    console.print(f"Workspace {home.root}", markup=False, highlight=False)
    for name in names:
        try:
            c = load_config(home.config_path(name), require_dump=False)
        except (OSError, TypeError, ValueError) as exc:
            console.print(f"  {name}  [red]{escape(str(exc))}[/red]", highlight=False)
            continue
        gitlab = c.gitlab_project or "[red]not set[/red]"
        budget = os.path.relpath(c.budgie_project, home.root)
        console.print(
            f"  [bold]{name}[/bold]  GitLab {gitlab}  Budgie {budget}", highlight=False
        )
        console.print(
            f"      dump {age(c.board_dump)} · weekly.csv "
            f"{age(c.budgie_project / 'weekly.csv')} · history {age(c.history)}",
            highlight=False,
        )


@cli.command()
@click.argument("name")
@click.option(
    "--home",
    "home_dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Make this directory the workspace (writes perch-home.yaml).",
)
@click.option(
    "--gitboard-dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="The remote-gitboard checkout; needed with --home the first time.",
)
def init(name, home_dir, gitboard_dir):
    """Scaffold projects/NAME/perch.yaml and the Budgie project budget/NAME."""
    from perch.core.steps import StepFailed, budgie_init
    from perch.core.workspace import HOME_NAME, check_name, create_home, load_home

    try:
        check_name(name)
        if home_dir is None:
            home = _find_home()
        elif (home_dir / HOME_NAME).is_file():
            home = load_home(home_dir / HOME_NAME)
        elif gitboard_dir is None:
            raise click.ClickException(
                f"{home_dir} has no {HOME_NAME} yet; pass --gitboard-dir "
                "<remote-gitboard checkout> too"
            )
        else:
            home = create_home(home_dir, gitboard_dir.expanduser().resolve())
        if home.config_path(name).exists():
            raise click.ClickException(
                f"{home.config_path(name)} exists; edit it instead."
            )
        if not (home.budget_dir(name) / "budgie.yaml").is_file():
            _run(budgie_init(_bin_dir(), home, name))
        path = home.scaffold(name)
    except StepFailed as exc:
        raise click.ClickException(f"{name}: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    budget = os.path.relpath(home.budget_dir(name), home.root)
    console.print(f"Wrote {path}. Fill in:", markup=False, highlight=False)
    console.print(
        f"  gitlab_project:  the GitLab path, e.g. group/{name}", markup=False
    )
    console.print(
        f"  people:          GitLab username -> name in {budget}/people.csv",
        markup=False,
    )
    console.print(f"  {budget}/  the Budgie inputs: budgie guide", markup=False)
    console.print(f"Then: perch doctor -p {name}", markup=False)


def _project(project):
    """(home, name, config) for -p, before the first fetch as much as after."""
    from perch.core.config import load_config

    home = _find_home()
    name = home.select(project, Path.cwd())
    return home, name, load_config(home.config_path(name), require_dump=False)


def _one(project, build) -> None:
    """Resolve the project, build its one step, run it; failures are clean errors."""
    from perch.core.steps import StepFailed

    name = project or "project"
    try:
        home, name, config = _project(project)
        _run(build(home, name, config))
    except StepFailed as exc:
        raise click.ClickException(f"{name}: {exc}") from exc
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@_project_option
def hours(project):
    """Step 0: open the project's weekly.csv to paste this week's timesheet totals."""
    from perch.core import steps

    console.print("One row per person: name,week,hours_to_date (cumulative).")
    editor = os.environ.get("EDITOR") or "vi"
    _one(project, lambda home, name, config: steps.hours(editor, config))


@cli.command()
@_project_option
def fetch(project):
    """Step 1: one GitLab read, gitboard stats into the project's board dump."""
    from perch.core import steps

    _one(project, steps.fetch)


@cli.command()
@_project_option
def digest(project):
    """Step 4: gitboard's team and per-person digest, from the same dump."""
    from perch.core import steps

    _one(project, steps.digest)


@cli.command()
@_project_option
def emails(project):
    """Step 5: Budgie's per-person hours-left drafts (.eml); nothing is sent."""
    from perch.core import steps

    _one(project, lambda home, name, config: steps.emails(_bin_dir(), config))


@cli.command()
@_project_option
def forecast(project):
    """Budgie's cost forecast for the project, with P10/P50/P90."""
    from perch.core import steps

    _one(project, lambda home, name, config: steps.forecast(_bin_dir(), config))


@cli.command()
@_project_option
def budget(project):
    """Which input files Budgie reads for the project, and what each feeds."""
    from perch.core import steps

    _one(project, lambda home, name, config: steps.budget(_bin_dir(), config))


@cli.command()
@_project_option
@click.option(
    "--all",
    "all_projects",
    is_flag=True,
    help="Every project, in name order; a failure moves on to the next.",
)
@click.option(
    "--from",
    "start",
    type=click.Choice(MONDAY_STEPS),
    default=None,
    help="Resume at this step instead of fetch.",
)
def monday(project, all_projects, start):
    """Steps 1-5: fetch, board, weekly, digest, emails. Run `perch hours` first.

    Nothing is ever sent: you review the drafts and send them yourself. Last,
    the private watch goes to projects/NAME/watch/, never beside the drafts.
    """
    from perch.core import steps
    from perch.core.config import load_config
    from perch.core.status import clear_failure, record_failure

    if project and all_projects:
        raise click.UsageError("give -p or --all, not both")
    if start and all_projects:
        raise click.UsageError("--from resumes one project: give -p, not --all")
    week = steps.iso_week(date.today())  # noqa: DTZ011 -- the lead's local Monday

    def run_one(home, name):
        config = load_config(home.config_path(name), require_dump=False)
        console.print(f"[bold]== {escape(name)}[/bold]", highlight=False)
        try:
            for step in steps.monday(_bin_dir(), home, name, config, week, start):
                _run(step)
        except steps.StepFailed as exc:
            # local naive time: status.py reads `at` back with fromisoformat()
            at = datetime.now()  # noqa: DTZ005
            record_failure(home, name, week, exc.step.name, exc.code, at)
            raise
        clear_failure(home, name)
        console.print(f"\n[bold]{name}[/bold] done. Review, then send yourself:")
        for place in (
            home.weekly_path(name, week),
            f"{home.reports_dir(name)}  (newest dated folder)",
            config.budgie_project / "emails",
        ):
            console.print(f"  {place}", markup=False, highlight=False)
        _write_watch(home, name, week)

    home = _home()
    if not all_projects:
        name = project or "project"
        try:
            name = home.select(project, Path.cwd())
            run_one(home, name)
        except steps.StepFailed as exc:
            raise click.ClickException(f"{name}: {exc}") from exc
        except (OSError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        return
    names = home.projects()
    if not names:
        raise click.ClickException("no projects yet. Run: perch init <name>")
    results = steps.run_projects(names, lambda name: run_one(home, name))
    console.print("\n[bold]monday --all[/bold]")
    for name, error in results:
        if error is None:
            console.print(f"  {name} ok", highlight=False)
        else:
            console.print(
                f"  [red]{name} FAILED[/red]: {escape(str(error))}", highlight=False
            )
    if any(error for _, error in results):
        raise click.exceptions.Exit(1)


_CELL = {  # state -> (shown, markup colour)
    "done": ("ok", "green"),
    "stale": ("stale", "yellow"),
    "todo": ("todo", "dim"),
    "failed": ("FAIL", "red"),
    "error": ("ERR", "red"),
}


@cli.command()
@_project_option
def status(project):
    """Each project's Monday steps: ok, stale, todo or FAIL, and the next command."""
    import shlex

    from perch.core import status as st

    home = _find_home()
    names = [home.select(project, Path.cwd())] if project else home.projects()
    if not names:
        raise click.ClickException("no projects yet. Run: perch init <name>")
    today = date.today()  # noqa: DTZ011 -- the lead's local Monday
    width = max(len(n) for n in names)
    console.print(" " * width + "".join(f"  {s:<6}" for s in st.STEPS), highlight=False)
    grid = {n: st.status(home, n, today) for n in names}
    for name, cells in grid.items():
        row = ""
        for step in st.STEPS:
            word, colour = _CELL[cells[step].state]
            row += f"  [{colour}]{word:<6}[/{colour}]"
        console.print(f"{escape(name):<{width}}{row}", highlight=False)
    for name, cells in grid.items():
        if (step := st.next_step(cells)) is None:
            continue
        if cells[step].state == "error":
            console.print(f"{escape(name)}: {escape(cells[step].why)}", highlight=False)
        else:
            cmd = shlex.join(st.next_command(name, step))
            console.print(f"next: {escape('perch ' + cmd)}", highlight=False)


def _runs(argv, cwd, env) -> bool:
    """Does this command exit 0? Quiet: doctor only wants the answer."""
    try:
        done = subprocess.run(
            argv, cwd=cwd, env={**os.environ, **env}, capture_output=True, check=False
        )
    except OSError:
        return False
    return done.returncode == 0


def _show_gitboard_config(home) -> bool:
    """Print gitboard's config table; True when it found a read token (exit 0)."""
    from perch.core.steps import gitboard

    step = gitboard(home, "gitboard config", "config")
    try:
        done = subprocess.run(
            step.argv, cwd=step.cwd, env={**os.environ, **step.env}, check=False
        )
    except OSError as exc:
        console.print(f"  [red]gitboard config did not run[/red]: {escape(str(exc))}")
        return False
    return done.returncode == 0


@cli.command()
@_project_option
def doctor(project):
    """Check the tools, each project's config, and how fresh the data is."""
    from perch.core.doctor import Check, freshness, project_checks, tool_checks

    home = _home()
    try:
        names = [home.select(project)] if project else home.projects()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    failed = 0

    def show(checks):
        nonlocal failed
        for c in checks:
            if c.ok:
                console.print(
                    f"  [green]ok[/green]    {escape(c.what)}", highlight=False
                )
            else:
                failed += 1
                console.print(
                    f"  [red]FIX[/red]   {escape(c.what)}  ->  {escape(c.fix)}",
                    highlight=False,
                )

    console.print(f"Workspace {home.root}", markup=False, highlight=False)
    console.print("[bold]Tools[/bold]")
    show(tool_checks(_bin_dir(), home, _runs))
    console.print("[bold]Projects[/bold]")
    if not names:
        show([Check(False, "no projects yet", "perch init <name>")])
    for name in names:
        show(project_checks(home, name))
    console.print("[bold]Data (last written)[/bold]")
    for name in names:
        for label, when in freshness(home, name):
            console.print(
                f"  {name}: {label:<14} {when}", markup=False, highlight=False
            )
    if home.gitboard_dir.is_dir():
        console.print("[bold]GitLab tokens (gitboard config)[/bold]")
        if not _show_gitboard_config(home):
            show(
                [
                    Check(
                        False,
                        "GitLab read token not found (or gitboard config failed)",
                        "see gitboard's README, 'Mint tokens'",
                    )
                ]
            )
    if failed:
        raise click.exceptions.Exit(1)


def _change(before, after, show) -> str:
    return f"{show(before)} → {show(after)}"


def _label(value: str | None) -> str:
    return "—" if value is None else value.upper()


@cli.command()
@_config_option
@_project_option
@click.option(
    "--budget",
    "new_budget",
    type=click.FloatRange(min=0, min_open=True),
    default=None,
    help="What-if: this budget instead of the latest.",
)
@click.option(
    "--leaves",
    multiple=True,
    metavar="NAME:YYYY-MM-DD",
    help="What-if: NAME is at 0 FTE from that date. Repeatable.",
)
@click.option(
    "--fte",
    multiple=True,
    metavar="NAME:YYYY-MM-DD:FTE",
    help="What-if: NAME is at FTE from that date. Repeatable.",
)
def cut(config_path, project, new_budget, leaves, fte):
    """What no longer fits after a budget cut or plan change. Writes nothing.

    With flags, today's files against today's files changed by the flags. With
    none, the last week `perch board` recorded against today's files.
    """
    from perch.core import money as m
    from perch.core.board import load_board
    from perch.core.config import load_config
    from perch.core.cut import compare, parse_change
    from perch.core.estimates import load_estimates
    from perch.core.history import latest_week
    from perch.core.join import calibrate, notes

    try:
        config = load_config(_config_path(config_path, project))
        the_board = load_board(config.board_dump)
        snap = m.load_snapshot(config.budgie_project)
        names = {p.name for p in snap.people}
        changes = [parse_change(f, names, snap.year, leaves=True) for f in leaves]
        changes += [parse_change(f, names, snap.year) for f in fte]
        now = m.money_from(snap)
        estimates = load_estimates(config.estimates) if config.estimates else {}
        rates = calibrate(now.readings, the_board, config.people, now.year)
        since = None
        if changes or new_budget is not None:
            before, after = now, m.money_from(m.what_if(snap, new_budget, changes))
            title = "What-if: today's files, then with the change"
        else:
            before, after = latest_week(config.history), now
            if not before:
                raise click.ClickException(
                    f"no week in {config.history} yet: run `perch board` first, "
                    "or give --budget/--leaves/--fte for a what-if"
                )
            since = before[0]["week"]
            title = f"Since {since}, the last week `perch board` recorded"
        result = compare(
            before, after, the_board, estimates, rates, config.people, changes
        )
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    b, a = result.before, result.after
    console.print(f"[bold]{escape(title)}[/bold]", highlight=False)
    for label, old, new, show in (
        ("Planned hours left", b.left, a.left, _hours),
        ("Budget", b.budget, a.budget, _money),
        ("Cost to clear (P50)", b.clear_p50, a.clear_p50, _money),
        ("Headroom", b.headroom, a.headroom, _money),
        ("Stoplight", b.signal, a.signal, _label),
    ):
        console.print(f"{label:<22}{_change(old, new, show)}", highlight=False)
    if result.spare is not None:
        if result.spare < 0:
            fits = f"[bold red]short by {_hours(-result.spare)} h[/bold red]"
        else:
            fits = f"hours still fit: {_hours(result.spare)} h spare"
        console.print(
            f"Board needs {_hours(result.board_hours)} h; the team has "
            f"{_hours(a.left)} h left after the change: {fits}",
            highlight=False,
            soft_wrap=True,
        )
    if since:
        console.print(
            f"[dim]Planned hours left also falls by the hours booked since {since}."
            "[/dim]",
            soft_wrap=True,
        )
    if b.old_row:
        console.print(
            "[yellow]![/yellow] That week was recorded before budget and hours "
            "left were; a fresh `perch board` will record them.",
            soft_wrap=True,
        )

    people = Table(title="People (name order)")
    for head in ("Name", "Hours left", "Open", "Hours", "Basis"):
        people.add_column(
            head, justify="left" if head in ("Name", "Basis") else "right"
        )
    for p in result.people:
        r = p.row
        people.add_row(
            p.name,
            _change(p.left_before, p.left_after, _hours),
            str(r.open) if r else "0",
            _spread(r.low, r.mode, r.high) if r else "—",
            (", ".join(r.bases) or "no basis") if r else "",
        )
    console.print(people)
    for p in result.people:
        if p.leaves is None:
            continue
        if p.row is None:
            console.print(
                f"{p.name} leaves {p.leaves}: no open issues", highlight=False
            )
            continue
        issues = "1 open issue" if p.row.open == 1 else f"{p.row.open} open issues"
        needs = "needs" if p.row.open == 1 else "need"
        console.print(
            f"{p.name} leaves {p.leaves}: {issues} "
            f"({_hours(p.row.mode)} h) {needs} a new owner: "
            + ", ".join(f"#{iid}" for iid in p.issues),
            highlight=False,
            soft_wrap=True,
        )

    milestones = Table(title="Milestones: open work")
    for head in ("Milestone", "Open", "Hours", "Due"):
        milestones.add_column(head, justify="left" if head == "Milestone" else "right")
    for ms in result.milestones:
        milestones.add_row(
            ms.name or "no milestone",
            str(ms.open),
            _spread(ms.low, ms.mode, ms.high)
            + (f" + {ms.no_basis} no basis" if ms.no_basis else ""),
            str(ms.due) if ms.due else "—",
        )
    console.print(milestones)
    for note in notes(
        the_board, [p.row for p in result.people if p.row], config.people, after
    ):
        console.print(f"[yellow]![/yellow] {note}")


def _watch(config_path: Path):
    """The private watch for one perch.yaml; perch's own read, no subprocess."""
    from perch.core.history import load
    from perch.core.watch import watch as build

    config, the_board, money, estimates, rates = _load(config_path)
    return build(
        the_board, money, rates, estimates, config.people, load(config.history)
    )


def _write_watch(home, name: str, week: str) -> None:
    """monday's last act: projects/NAME/watch/WEEK.md, and one line."""
    from perch.core.watch import render, summary

    # The drafts are written by now: a watch that can't be read must not fail them.
    try:
        page = _watch(home.config_path(name))
        path = home.watch_path(name, week)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(page))
    except (OSError, TypeError, ValueError) as exc:
        console.print(f"watch: could not be read: {exc}", markup=False, highlight=False)
        return
    console.print(summary(page), markup=False, highlight=False)


@cli.command()
@_config_option
@_project_option
@click.option(
    "--all",
    "all_projects",
    is_flag=True,
    help="Every project, in name order; a failure moves on to the next.",
)
def watch(config_path, project, all_projects):
    """Private: anyone out of line with their own last 8 weeks. For you only."""
    from perch.core.steps import run_projects
    from perch.core.watch import render

    if all_projects and (project or config_path):
        raise click.UsageError("give -p/--config or --all, not both")
    if not all_projects:
        try:
            page = _watch(_config_path(config_path, project))
        except (OSError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(render(page), nl=False)
        return
    home = _home()
    if not home.projects():
        raise click.ClickException("no projects yet. Run: perch init <name>")
    results = run_projects(
        home.projects(),
        lambda name: click.echo(render(_watch(home.config_path(name)))),
    )
    for name, error in results:
        if error is not None:
            console.print(
                f"[red]{name} FAILED[/red]: {escape(str(error))}", highlight=False
            )
    if any(error for _, error in results):
        raise click.exceptions.Exit(1)


def _write_quarterly(config_path: Path, quarter: str | None, out: Path | None):
    """Load one project, build its quarter, write the .eml and .md beside it."""
    from perch.core.board import load_board
    from perch.core.config import load_config
    from perch.core.estimates import load_estimates
    from perch.core.join import calibrate
    from perch.core.money import load_money
    from perch.core.quarterly import build, last_complete_quarter
    from perch.core.report_mail import render_eml, render_md

    config = load_config(config_path, require_dump=False)
    board = load_board(config.board_dump) if config.board_dump.is_file() else None
    money = load_money(config.budgie_project)
    estimates = load_estimates(config.estimates) if config.estimates else {}
    rates = (
        calibrate(money.readings, board, config.people, money.year) if board else None
    )
    today = date.today()  # noqa: DTZ011 -- the lead's local date
    report = build(
        board,
        money,
        estimates,
        rates,
        config.people,
        quarter or last_complete_quarter(money.year, today),
        today,
        config.root.name,
    )
    folder = out or config.root / "quarterly"
    folder.mkdir(parents=True, exist_ok=True)
    eml = folder / f"{report.name}.eml"
    eml.write_bytes(bytes(render_eml(report)))
    md = eml.with_suffix(".md")
    md.write_text(render_md(report))
    for path in (eml, md):
        click.echo(f"Wrote {path}")


@cli.command()
@_config_option
@_project_option
@click.option(
    "--all",
    "all_projects",
    is_flag=True,
    help="Every project, in name order; a failure moves on to the next.",
)
@click.option(
    "--quarter", default=None, help="e.g. 2026-Q3; default the last complete one."
)
@click.option(
    "--out",
    "out_dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Write here instead of projects/<name>/quarterly/ (--all: one folder each).",
)
def quarterly(config_path, project, all_projects, quarter, out_dir):
    """The quarter's money for the funder: an Outlook draft (.eml) and a .md.

    Nothing is sent: open the draft in Outlook, review it, send it yourself.
    """
    from perch.core import steps

    if all_projects and (project or config_path):
        raise click.UsageError("give -p or --all, not both")
    if not all_projects:
        try:
            _write_quarterly(_config_path(config_path, project), quarter, out_dir)
        except (OSError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        return
    home = _home()
    names = home.projects()
    if not names:
        raise click.ClickException("no projects yet. Run: perch init <name>")
    results = steps.run_projects(
        names,
        lambda name: _write_quarterly(
            home.config_path(name), quarter, out_dir / name if out_dir else None
        ),
    )
    console.print("\n[bold]quarterly --all[/bold]")
    for name, error in results:
        if error is None:
            console.print(f"  {name} ok", highlight=False)
        else:
            console.print(
                f"  [red]{name} FAILED[/red]: {escape(str(error))}", highlight=False
            )
    if any(error for _, error in results):
        raise click.exceptions.Exit(1)


@cli.command()
def tui():
    """Every project in one table; single keys run perch on the selected one."""
    from perch import tui as tui_mod

    target = tui_mod.PerchTUI(_home()).run()
    if target:
        tui_mod.switch(tui_mod.suite_entry(target))
