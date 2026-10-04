"""scripts/bootstrap.sh: clones the two apps into apps/, and only once.

Runs the real script against throwaway local repos (file:// URLs) in a copy of
it, with the install step off, so nothing outside tmp_path is touched.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.sh"


def _repo(path: Path) -> str:
    path.mkdir()
    git = ["git", "-C", str(path)]
    subprocess.run([*git, "init", "-q"], check=True)
    (path / "README.md").write_text("x\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run(
        [*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
        check=True,
    )
    return path.as_uri()


@pytest.fixture
def perch(tmp_path):
    root = tmp_path / "perch"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "bootstrap.sh")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(tmp_path),
        "BUDGIE_URL": _repo(tmp_path / "budgie-src"),
        "GB_URL": _repo(tmp_path / "gb-src"),
        "BOOTSTRAP_NO_INSTALL": "1",
    }
    return root, env


def _run(root, env, cwd):
    return subprocess.run(
        ["sh", str(root / "scripts" / "bootstrap.sh")],
        cwd=cwd, env=env, capture_output=True, text=True, check=False,
    )


def test_clones_both_apps_from_anywhere_and_names_gitboard_dir(perch, tmp_path):
    root, env = perch
    out = _run(root, env, cwd=tmp_path)  # not perch's root
    assert out.returncode == 0, out.stderr
    assert (root / "apps" / "budgie" / ".git").is_dir()
    assert (root / "apps" / "remote-gitboard" / ".git").is_dir()
    last = out.stdout.strip().splitlines()[-1]
    assert last == f"gitboard_dir: {root.resolve()}/apps/remote-gitboard"


def test_second_run_leaves_the_checkouts_alone(perch, tmp_path):
    root, env = perch
    assert _run(root, env, cwd=root).returncode == 0
    marker = root / "apps" / "budgie" / "local-edit"
    marker.write_text("mine\n")
    out = _run(root, env, cwd=root)
    assert out.returncode == 0, out.stderr
    assert "cloning" not in out.stdout
    assert marker.read_text() == "mine\n"


def test_an_app_dir_that_is_not_a_checkout_stops_it(perch):
    root, env = perch
    (root / "apps" / "budgie").mkdir(parents=True)
    out = _run(root, env, cwd=root)
    assert out.returncode != 0
    assert "apps/budgie" in out.stderr
    assert not (root / "apps" / "remote-gitboard").exists()


def test_a_failed_clone_names_the_app_and_leaves_nothing(perch, tmp_path):
    root, env = perch
    env = {**env, "GB_URL": (tmp_path / "missing").as_uri()}
    out = _run(root, env, cwd=root)
    assert out.returncode != 0
    assert "remote-gitboard" in out.stderr
    assert not (root / "apps" / "remote-gitboard").exists()
