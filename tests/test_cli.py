"""CLI entry-point tests.

Covers the two ways the package is invoked:

* ``python -m c2pw_convert ...`` — the ``__main__`` module.
* Direct import — must NOT run the CLI as a side effect (regression fix #8).
"""

import json
import subprocess
import sys
from pathlib import Path

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.json"
REPO_ROOT = Path(__file__).parent.parent


def test_importing_main_module_does_not_exit():
    """__main__.py must be guarded by ``if __name__ == '__main__'``.

    Prior to the fix, ``import c2pw_convert.__main__`` unconditionally
    invoked the CLI and raised SystemExit(2) because no argv was passed.
    """
    import importlib

    # If the guard is missing, this raises SystemExit and the test fails.
    module = importlib.import_module("c2pw_convert.__main__")
    assert hasattr(module, "main")


def test_python_dash_m_help_exits_zero():
    """The module invocation path still works after adding the guard."""
    result = subprocess.run(
        [sys.executable, "-m", "c2pw_convert", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "c2pw-convert" in result.stdout
    assert "--to" in result.stdout


def test_python_dash_m_end_to_end_bitwarden():
    """End-to-end: the real JSON export goes in, Bitwarden JSON comes out."""
    result = subprocess.run(
        [sys.executable, "-m", "c2pw_convert", str(REAL_EXPORT), "--to", "bitwarden"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    cipher = payload["items"][0]
    assert cipher["name"] == "login type item - display name"
    assert cipher["login"]["password"] == "password value"


def test_bitwarden_warns_when_output_is_named_csv(tmp_path):
    """--to bitwarden used to mean CSV; a stale .csv path must not be silent."""
    out = tmp_path / "vault.csv"
    result = subprocess.run(
        [
            sys.executable, "-m", "c2pw_convert", str(REAL_EXPORT),
            "--to", "bitwarden", "-o", str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "writes JSON" in result.stderr
    assert json.loads(out.read_text())["items"]



# ---- Item-type reporting ---------------------------------------------------

ITEM_TYPES_FIXTURE = REAL_EXPORT


def _run(target: str):
    return subprocess.run(
        [sys.executable, "-m", "c2pw_convert", str(ITEM_TYPES_FIXTURE), "--to", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_summary_breaks_down_item_types_on_stderr():
    result = _run("keepassxc")
    assert result.returncode == 0, result.stderr
    assert "Payment card: 1" in result.stderr
    assert "Contact information: 1" in result.stderr
    # The CSV itself must stay clean for piping.
    assert result.stdout.startswith("Group,Title,Username")


def test_login_only_target_warns_about_skipped_items():
    result = _run("chrome")
    assert result.returncode == 0, result.stderr
    assert "can only import logins" in result.stderr
    assert "skipped 4 non-login item(s)" in result.stderr


def test_bitwarden_target_emits_json_and_flags_degraded_items():
    result = _run("bitwarden")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # Login, Secure Note, Card and Identity all map to a native cipher type.
    assert {i["type"] for i in payload["items"]} == {1, 2, 3, 4}
    assert "have no native Bitwarden type" not in result.stderr
