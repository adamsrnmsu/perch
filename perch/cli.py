"""The perch command line: a thin adapter over perch.core."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

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
    """--config wins; then -p in the workspace; outside one, ./perch.yaml."""
    from perch.core.config import CONFIG_NAME
    from perch.core.workspace import WorkspaceError

    if config_path:
        return Path(config_path)
    try:
        home = _find_home()
    except WorkspaceError:
        if project is None and Path(CONFIG_NAME).is_file():
            return Path(CONFIG_NAME)
        raise
    return home.config_path(home.select(project))


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


@click.group()
def cli():
    """perch -- what the open board means for the budget."""


@cli.command()
@_config_option
@_project_option
@click.option("--seed", default=None, type=int, help="Seed the simulation.")
@click.option("--iterations", default=None, type=int, help="Simulation draws.")
@click.option("--no-history", is_flag=True, help="Don't append to history.jsonl.")
def board(config_path, project, seed, iterations, no_history):
    """Cost to clear the open board, against the hours and budget left."""
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
            rows_for(rows, rates, summary, accuracy if estimates else ()),
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
    """Per-person markdown drafts for the weekly digest. Nothing is sent."""
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
    name = home.select(project)
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
def monday(project, all_projects):
    """Steps 1-5: fetch, board, weekly, digest, emails. Run `perch hours` first.

    Nothing is ever sent: you review the drafts and send them yourself.
    """
    from perch.core import steps
    from perch.core.config import load_config

    if project and all_projects:
        raise click.UsageError("give -p or --all, not both")
    week = steps.iso_week(date.today())  # noqa: DTZ011 -- the lead's local Monday

    def run_one(home, name):
        config = load_config(home.config_path(name), require_dump=False)
        console.print(f"[bold]== {escape(name)}[/bold]", highlight=False)
        for step in steps.monday(_bin_dir(), home, name, config, week):
            _run(step)
        console.print(f"\n[bold]{name}[/bold] done. Review, then send yourself:")
        for place in (
            home.weekly_path(name, week),
            f"{home.reports_dir(name)}  (newest dated folder)",
            config.budgie_project / "emails",
        ):
            console.print(f"  {place}", markup=False, highlight=False)

    home = _home()
    if not all_projects:
        name = project or "project"
        try:
            name = home.select(project)
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


def _runs(argv, cwd, env) -> bool:
    """Does this command exit 0? Quiet: doctor only wants the answer."""
    try:
        done = subprocess.run(
            argv, cwd=cwd, env={**os.environ, **env}, capture_output=True, check=False
        )
    except OSError:
        return False
    return done.returncode == 0


def _show_gitboard_config(home) -> None:
    from perch.core.steps import gitboard

    step = gitboard(home, "gitboard config", "config")
    try:
        subprocess.run(
            step.argv, cwd=step.cwd, env={**os.environ, **step.env}, check=False
        )
    except OSError as exc:
        console.print(f"  [red]gitboard config did not run[/red]: {escape(str(exc))}")


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
        _show_gitboard_config(home)
    if failed:
        raise click.exceptions.Exit(1)
