"""make install's helper: what to pip install, and the commands that run from source.

Nothing of ours is built or installed. perch, Budgie and gitboard run from
their checkouts on PYTHONPATH, so there is no .pth file for macOS's hidden
flag to break, and no build backend (setuptools, hatchling) to download when
the machine is offline.

    python scripts/install_env.py requirements PERCH_DIR   # one requirement per line
    python scripts/install_env.py wrappers PERCH_DIR BIN    # perch, budgie, gitboard in BIN
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

import tomllib

APPS = (".", "apps/budgie", "apps/remote-gitboard")
SOURCES = (".", "apps/budgie", "apps/remote-gitboard/src")
EXTRAS = ("dev", "docs")


def _project(perch: Path, app: str) -> dict:
    return tomllib.loads((perch / app / "pyproject.toml").read_text())["project"]


def requirements(perch: Path) -> list[str]:
    """Every app's dependencies plus its dev and docs extras, first seen first.

    A URL requirement (perch's `budgie @ git+...`) is left out: that app is on
    PYTHONPATH from its checkout instead.
    """
    out: list[str] = []
    for app in APPS:
        project = _project(perch, app)
        extras = project.get("optional-dependencies", {})
        for req in [
            *project.get("dependencies", []),
            *(r for e in EXTRAS for r in extras.get(e, [])),
        ]:
            if "@" not in req and req not in out:
                out.append(req)
    return out


def pythonpath(perch: Path) -> str:
    return ":".join(str(perch / s) if s != "." else str(perch) for s in SOURCES)


def wrappers(perch: Path, bin_dir: Path) -> list[Path]:
    """One sh script per [project.scripts] entry, where a console script would be."""
    python = shlex.quote(str(bin_dir / "python"))
    env = shlex.quote(f"PYTHONPATH={pythonpath(perch)}")
    written = []
    for app in APPS:
        for name, target in _project(perch, app).get("scripts", {}).items():
            module, func = target.split(":")
            code = (
                f'import sys; sys.argv[0] = "{name}"; '
                f"from {module} import {func}; sys.exit({func}())"
            )
            path = bin_dir / name
            path.unlink(
                missing_ok=True
            )  # an old symlink is replaced, never written through
            path.write_text(
                "#!/bin/sh\n"
                "# Written by perch's make install: runs the checkout's source.\n"
                f'exec env {env} {python} -P -c {shlex.quote(code)} "$@"\n'
            )
            path.chmod(0o755)
            written.append(path)
    return written


def main(argv: list[str]) -> int:
    if argv[:1] == ["requirements"] and len(argv) == 2:
        print("\n".join(requirements(Path(argv[1]).resolve())))
        return 0
    if argv[:1] == ["wrappers"] and len(argv) == 3:
        for path in wrappers(Path(argv[1]).resolve(), Path(argv[2])):
            print(f"wrote {path}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
