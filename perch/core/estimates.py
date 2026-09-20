"""estimates.csv: business estimates, massaged into one flat shape.

    key,hours,low,high
    #14,24,,
    epic::billing,400,320,520

A key starting with `#` is one issue by iid; any other key is a label and
covers every issue carrying it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from budgie.core.csvio import as_float, as_required_float, as_str, read_rows


@dataclass(frozen=True)
class Estimate:
    key: str
    low: float
    hours: float
    high: float

    @property
    def is_issue(self) -> bool:
        return self.key.startswith("#")


def issue_key(iid: int) -> str:
    return f"#{iid}"


def load_estimates(path: str | Path) -> dict[str, Estimate]:
    out: dict[str, Estimate] = {}
    for row in read_rows(path, required={"key", "hours"}):
        key = as_str(row, "key")
        if key in out:
            raise ValueError(f"{Path(path).name}: `{key}` appears more than once")
        hours = as_required_float(row, "hours")
        low = as_float(row, "low", hours)
        high = as_float(row, "high", hours)
        if not 0 <= low <= hours <= high:
            raise ValueError(
                f"{Path(path).name}: `{key}` needs 0 <= low <= hours <= high, "
                f"got ({low:g}, {hours:g}, {high:g})"
            )
        out[key] = Estimate(key, low, hours, high)
    return out
