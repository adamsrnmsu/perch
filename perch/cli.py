"""The perch command line: a thin adapter over perch.core."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
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


def _load(config_path):
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
    default="perch.yaml",
    show_default=True,
    help="The perch.yaml naming the Budgie project and the gitboard dump.",
)


@click.group()
def cli():
    """perch -- what the open board means for the budget."""


@cli.command()
@_config_option
@click.option("--seed", default=None, type=int, help="Seed the simulation.")
@click.option("--iterations", default=None, type=int, help="Simulation draws.")
@click.option("--no-history", is_flag=True, help="Don't append to history.jsonl.")
def board(config_path, seed, iterations, no_history):
    """Cost to clear the open board, against the hours and budget left."""
    from perch.core.accuracy import by_person
    from perch.core.history import record, rows_for
    from perch.core.join import notes, person_rows, rollup

    try:
        config, the_board, money, estimates, rates = _load(config_path)
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
def accuracy(config_path):
    """How estimates compared with what the work took."""
    from perch.core.accuracy import by_label, by_person

    try:
        config, the_board, money, estimates, rates = _load(config_path)
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
@click.option("--person", default=None, help="Only this person (a name in `people:`).")
@click.option("--out", "out_path", default=None, help="Write the markdown here.")
def weekly(config_path, person, out_path):
    """Per-person markdown drafts for the weekly digest. Nothing is sent."""
    from perch.core.accuracy import by_person
    from perch.core.history import load
    from perch.core.join import person_rows
    from perch.core.weekly import weekly as render

    try:
        config, the_board, money, estimates, rates = _load(config_path)
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
