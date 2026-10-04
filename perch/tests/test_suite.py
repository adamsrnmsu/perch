"""perch suite: tmux argv for the launch and the hop (core/suite.py), and the
`perch suite` command that runs them."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from perch import tui
from perch.cli import cli
from perch.core import suite
from perch.tests.conftest import build_home

TMUX = ["tmux", "-L", "pi"]
B = {"cwd": "/ws/budget/fy26", "argv": ["/venv/bin/budgie", "tui"]}
B_KEY = json.dumps(B, sort_keys=True)


def test_in_suite_only_on_the_pi_socket():
    assert suite.in_suite({"TMUX": "/private/tmp/tmux-501/pi,123,0"})
    assert not suite.in_suite({"TMUX": "/private/tmp/tmux-501/default,123,0"})
    assert not suite.in_suite({})


def test_entry_key_ignores_key_order():
    assert suite.entry_key({"argv": ["a"], "cwd": "/x"}) == suite.entry_key(
        {"cwd": "/x", "argv": ["a"]}
    )


def test_entry_of_reads_the_window_listing():
    listing = f"perch\t{{}}\nbudgie\t{B_KEY}\nodd\t\n"
    assert suite.entry_of(listing, "budgie") == B_KEY
    assert suite.entry_of(listing, "odd") == ""  # a window with no @entry
    assert suite.entry_of(listing, "gitboard") is None  # no window


def test_windows_lists_name_and_entry():
    assert suite.windows() == [
        *TMUX,
        "list-windows",
        "-t",
        "pi",
        "-F",
        "#{window_name}\t#{@entry}",
    ]


def test_hop_to_the_same_entry_only_selects():
    assert suite.hop("budgie", B, "{}", B_KEY) == [
        *TMUX,
        "select-window",
        "-t",
        "pi:=budgie",
    ]


def test_hop_to_a_missing_window_opens_it():
    assert suite.hop("budgie", B, '{"m": 1}', None) == [
        *TMUX,
        "new-window",
        "-t",
        "pi:",
        "-n",
        "budgie",
        "-c",
        "/ws/budget/fy26",
        "-e",
        'PI_SUITE={"m": 1}',
        "/venv/bin/budgie",
        "tui",
        ";",
        "set-option",
        "-w",
        "-t",
        "pi:=budgie",
        "@entry",
        B_KEY,
    ]


def test_hop_to_another_entry_respawns_only_that_window():
    other = json.dumps({"cwd": "/ws/budget/fy27", "argv": ["/venv/bin/budgie", "tui"]})
    assert suite.hop("budgie", B, "{}", other) == [
        *TMUX,
        "respawn-window",
        "-k",
        "-t",
        "pi:=budgie",
        "-c",
        "/ws/budget/fy26",
        "-e",
        "PI_SUITE={}",
        "/venv/bin/budgie",
        "tui",
        ";",
        "set-option",
        "-w",
        "-t",
        "pi:=budgie",
        "@entry",
        B_KEY,
        ";",
        "select-window",
        "-t",
        "pi:=budgie",
    ]


def test_hop_without_a_recorded_entry_respawns():
    assert suite.hop("budgie", B, "{}", "")[3:5] == ["respawn-window", "-k"]


def test_launch_sets_every_option_before_the_first_window():
    m = {
        "perch": {"cwd": "/ws", "argv": ["/venv/bin/perch", "tui"]},
        "budgie": B,
        "gitboard": {"cwd": "/gb", "argv": ["gitboard", "tui", "grp/a"]},
    }
    argv = suite.launch(m["perch"], m)
    assert argv[:6] == [*TMUX, "-f", "/dev/null", "start-server"]
    first_window = argv.index("new-session")
    for flag, option, value in suite.OPTIONS:
        at = argv.index(option)
        assert argv[at - 1 : at + 2] == [flag, option, value]
        assert at < first_window
    env = f"PI_SUITE={json.dumps(m)}"
    assert argv[first_window : first_window + 13] == [
        "new-session",
        "-d",
        "-s",
        "pi",
        "-n",
        "perch",
        "-c",
        "/ws",
        "-e",
        env,
        "/venv/bin/perch",
        "tui",
        ";",
    ]
    assert argv.count("new-window") == 2
    for name in ("perch", "budgie", "gitboard"):
        at = argv.index(f"pi:={name}")
        assert argv[at + 1 : at + 3] == ["@entry", suite.entry_key(m[name])]
    assert argv[-4:] == [";", "select-window", "-t", "pi:=perch"]


def test_launch_without_a_map_starts_perch_alone():
    perch = {"cwd": "/ws", "argv": ["/venv/bin/perch", "tui"]}
    argv = suite.launch(perch, None)
    at = argv.index("new-session")
    assert argv[at:] == [
        "new-session",
        "-d",
        "-s",
        "pi",
        "-n",
        "perch",
        "-c",
        "/ws",
        "/venv/bin/perch",
        "tui",
        ";",
        "set-option",
        "-w",
        "-t",
        "pi:=perch",
        "@entry",
        suite.entry_key(perch),
        ";",
        "select-window",
        "-t",
        "pi:=perch",
    ]
    assert "new-window" not in argv


def test_launch_keeps_a_cwd_with_spaces_whole():
    m = {
        "perch": {"cwd": "/ws", "argv": ["perch", "tui"]},
        "budgie": {"cwd": "/ws/budget/My Budget", "argv": ["budgie", "tui"]},
        "gitboard": {"cwd": "/gb", "argv": ["gitboard", "tui"]},
    }
    argv = suite.launch(m["perch"], m)
    assert argv[argv.index("/ws/budget/My Budget") - 1] == "-c"


def test_session_commands():
    assert suite.has_session() == [*TMUX, "has-session", "-t", "pi"]
    assert suite.attach() == [*TMUX, "attach", "-t", "pi"]
    assert suite.kill() == [*TMUX, "kill-session", "-t", "pi"]


# --- perch suite ---------------------------------------------------------------


@pytest.fixture
def tmux(monkeypatch):
    """tmux on PATH; records each argv and env. has-session fails until .up."""
    calls = []

    class Fake:
        up = False

    def run(argv, **kw):
        calls.append((list(argv), kw.get("env")))
        code = 0 if "has-session" not in argv or Fake.up else 1
        return subprocess.CompletedProcess(argv, code, "", "")

    Fake.execs = []
    Fake.calls = calls
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/tmux")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("os.execvpe", lambda f, a, env: Fake.execs.append((f, a, env)))
    monkeypatch.setenv(
        "TMUX", "/tmp/tmux-501/default,1,0"
    )  # started from the user's tmux
    return Fake


def _perch(home):
    return {
        "cwd": str(home.root),
        "argv": [str(Path(sys.executable).parent / "perch"), "tui"],
    }


def test_suite_without_tmux_says_how_to_get_it(tmp_path, monkeypatch):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setattr("shutil.which", lambda name: None)
    r = CliRunner().invoke(cli, ["suite"])
    assert r.exit_code == 1
    assert "needs tmux: brew install tmux" in r.output


def test_suite_running_just_attaches_outside_the_users_tmux(
    tmp_path, monkeypatch, tmux
):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    tmux.up = True
    assert CliRunner().invoke(cli, ["suite"]).exit_code == 0
    assert [argv for argv, _ in tmux.calls] == [suite.has_session()]
    ((file, argv, env),) = tmux.execs
    assert (file, argv) == ("tmux", suite.attach())
    assert "TMUX" not in env


def test_suite_cold_start_launches_then_attaches(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    assert CliRunner().invoke(cli, ["suite"]).exit_code == 0
    launched = [argv for argv, _ in tmux.calls][1]
    assert launched == suite.launch(_perch(home), tui.suite_map(home, "apollo"))
    assert "TMUX" not in tmux.calls[1][1]
    assert tmux.execs[0][1] == suite.attach()


def test_suite_without_p_opens_on_the_first_project(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo", "beta")
    monkeypatch.chdir(tmp_path / "ws")
    assert CliRunner().invoke(cli, ["suite"]).exit_code == 0
    assert tmux.calls[1][0] == suite.launch(_perch(home), tui.suite_map(home, "apollo"))


def test_suite_p_picks_the_project(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo", "beta")
    monkeypatch.chdir(tmp_path / "ws")
    assert CliRunner().invoke(cli, ["suite", "-p", "beta"]).exit_code == 0
    assert tmux.calls[1][0] == suite.launch(_perch(home), tui.suite_map(home, "beta"))


def test_suite_unknown_project_starts_nothing(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    r = CliRunner().invoke(cli, ["suite", "-p", "nosuch"])
    assert r.exit_code == 1
    assert "no project 'nosuch'" in r.output and "apollo" in r.output
    assert [argv for argv, _ in tmux.calls] == [suite.has_session()]
    assert tmux.execs == []


def test_suite_bad_config_starts_perch_alone(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo")
    home.config_path("apollo").write_text("people: {}\n")  # no budgie_project
    monkeypatch.chdir(tmp_path / "ws")
    r = CliRunner().invoke(cli, ["suite"])
    assert r.exit_code == 0
    assert "budgie_project" in r.output and "perch only" in r.output
    assert tmux.calls[1][0] == suite.launch(_perch(home), None)


def test_suite_tmux_refusing_to_start_says_why(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")

    def run(argv, **kw):
        if "start-server" in argv:
            return subprocess.CompletedProcess(
                argv, 1, "", "unknown option: focus-events"
            )
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    r = CliRunner().invoke(cli, ["suite"])
    assert r.exit_code == 1
    assert "unknown option: focus-events" in r.output
    assert tmux.execs == []


# --- perch tui starts the suite --------------------------------------------------


def _no_tui(monkeypatch):
    """Records each PerchTUI.run instead of drawing it."""
    ran = []

    def run(self):
        ran.append(self)

    monkeypatch.setattr(tui.PerchTUI, "run", run)
    return ran


def test_perch_tui_with_tmux_starts_the_suite(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    drawn = _no_tui(monkeypatch)
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert [argv for argv, _ in tmux.calls] == [
        suite.has_session(),
        suite.launch(_perch(home), tui.suite_map(home, "apollo")),
    ]
    assert tmux.execs[0][1] == suite.attach()
    assert drawn == []


def test_perch_tui_reattaches_a_running_suite(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    tmux.up = True
    drawn = _no_tui(monkeypatch)
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert [argv for argv, _ in tmux.calls] == [suite.has_session()]
    assert drawn == []


def test_perch_tui_inside_the_suite_draws_the_tui(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setenv("TMUX", "/private/tmp/tmux-501/pi,123,0")
    drawn = _no_tui(monkeypatch)
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert len(drawn) == 1
    assert [argv for argv, _ in tmux.calls] == [suite.kill()]  # q closes the suite


def test_perch_tui_without_tmux_draws_the_tui(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setattr("shutil.which", lambda name: None)
    drawn = _no_tui(monkeypatch)
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert len(drawn) == 1
    assert tmux.calls == [] and tmux.execs == []


def test_perch_tui_no_suite_draws_the_tui(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    drawn = _no_tui(monkeypatch)
    assert CliRunner().invoke(cli, ["tui", "--no-suite"]).exit_code == 0
    assert len(drawn) == 1
    assert tmux.calls == [] and tmux.execs == []
