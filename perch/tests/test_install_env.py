"""scripts/install_env.py: what make install pip-installs and the wrappers it writes."""

import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_env.py"


def _venv():
    spec = importlib.util.spec_from_file_location("install_env", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _app(root, rel, text):
    (root / rel).mkdir(parents=True, exist_ok=True)
    (root / rel / "pyproject.toml").write_text(text)


def _checkout(tmp_path):
    _app(
        tmp_path,
        ".",
        """
[project]
name = "perch"
dependencies = ["budgie @ git+https://example.invalid/budgie.git", "click", "rich"]
[project.optional-dependencies]
dev = ["pytest>=6.2.4"]
docs = ["sphinx"]
other = ["never"]
[project.scripts]
perch = "perch.cli:cli"
""",
    )
    _app(
        tmp_path,
        "apps/budgie",
        """
[project]
name = "Budgie"
dependencies = ["click", "numpy"]
[project.scripts]
budgie = "budgie.budgie:cli"
""",
    )
    _app(
        tmp_path,
        "apps/remote-gitboard",
        """
[project]
name = "gitboard"
dependencies = ["python-gitlab"]
[project.optional-dependencies]
dev = ["pytest"]
[project.scripts]
gitboard = "gitboard.cli:app"
""",
    )
    return tmp_path


def test_requirements_are_every_apps_deps_and_dev_docs_extras_minus_urls(tmp_path):
    reqs = _venv().requirements(_checkout(tmp_path))
    assert reqs == [
        "click",
        "rich",
        "pytest>=6.2.4",
        "sphinx",
        "numpy",
        "python-gitlab",
        "pytest",
    ]


def test_wrappers_run_each_entry_point_from_source(tmp_path):
    perch = _checkout(tmp_path)
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "perch").symlink_to(
        tmp_path / "elsewhere"
    )  # an old link is replaced, not followed
    written = _venv().wrappers(perch, bin_dir)
    assert [p.name for p in written] == ["perch", "budgie", "gitboard"]
    assert not (tmp_path / "elsewhere").exists()
    text = (bin_dir / "gitboard").read_text()
    assert text.startswith("#!/bin/sh\n")
    path = f"{perch}:{perch}/apps/budgie:{perch}/apps/remote-gitboard/src"
    assert f"PYTHONPATH={path}" in text
    assert "from gitboard.cli import app" in text and 'sys.argv[0] = "gitboard"' in text
    assert (
        " -P -c " in text
    )  # -P: the cwd (projects/NAME, a budget dir) never shadows a module
    assert (bin_dir / "gitboard").stat().st_mode & 0o111


def test_a_wrapper_actually_runs(tmp_path):
    perch = _checkout(tmp_path)
    pkg = perch / "apps" / "remote-gitboard" / "src" / "gitboard"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(
        "import sys\ndef app():\n    print(sys.argv[0], *sys.argv[1:])\n    return 0\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(Path(__import__("sys").executable))
    _venv().wrappers(perch, bin_dir)
    out = subprocess.run(
        [str(bin_dir / "gitboard"), "show", "a b"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout == "gitboard show a b\n"
