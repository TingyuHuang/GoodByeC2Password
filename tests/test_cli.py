"""CLI entry-point tests.

Covers the two ways the package is invoked:

* ``python -m c2pw_convert ...`` — the ``__main__`` module.
* Direct import — must NOT run the CLI as a side effect (regression fix #8).
"""

import subprocess
import sys
from pathlib import Path

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.csv"
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
    """End-to-end: real export goes in, Bitwarden CSV comes out via stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "c2pw_convert", str(REAL_EXPORT), "--to", "bitwarden"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    # Header line plus the one data row's identifying fields.
    assert result.stdout.startswith(
        "folder,favorite,type,name,notes,fields,reprompt,"
        "login_uri,login_username,login_password,login_totp"
    )
    assert "login display name" in result.stdout
    assert "login password" in result.stdout

