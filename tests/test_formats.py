"""Tests for the additional password manager CSV writers.

Each test drives a writer with the real C2 export fixture
(``tests/C2Password_Export.csv``) and asserts the resulting CSV's headers
plus the destination of every meaningful field. Custom fields and extra
URLs always need to land somewhere, even if it's the notes blob.
"""

import csv
import io
from pathlib import Path

import pytest

from c2pw_convert import (
    parse_c2_csv,
    write_apple_csv,
    write_chrome_csv,
    write_dashlane_csv,
    write_firefox_csv,
    write_keepassxc_csv,
    write_lastpass_csv,
    write_nordpass_csv,
    write_proton_csv,
)

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.csv"
SYNTHETIC = Path(__file__).parent / "fixtures" / "sample_c2.csv"


def _real():
    return parse_c2_csv(REAL_EXPORT)


def _synthetic():
    return parse_c2_csv(SYNTHETIC)


def _read(writer, items):
    buf = io.StringIO()
    writer(items, buf)
    buf.seek(0)
    return list(csv.DictReader(buf)), csv.reader(io.StringIO(buf.getvalue())).__next__()


# ---------- KeePassXC ------------------------------------------------------


def test_keepassxc_columns_and_row():
    rows, headers = _read(write_keepassxc_csv, _real())
    assert headers == ["Group", "Title", "Username", "Password", "URL", "Notes", "TOTP"]
    row = rows[0]
    assert row["Title"] == "login display name"
    assert row["Username"] == "login username"
    assert row["Password"] == "login password"
    assert row["URL"] == "URL1"
    assert "URL2" in row["Notes"]
    assert "custom text key: custom text value" in row["Notes"]
    assert row["TOTP"].startswith("otpauth://totp/")
    assert "secret=2FA" in row["TOTP"]


# ---------- LastPass --------------------------------------------------------


def test_lastpass_columns_and_row():
    rows, headers = _read(write_lastpass_csv, _real())
    assert headers == ["url", "username", "password", "totp", "extra", "name", "grouping", "fav"]
    row = rows[0]
    assert row["name"] == "login display name"
    assert row["url"] == "URL1"
    assert row["username"] == "login username"
    assert row["password"] == "login password"
    assert row["totp"] == "2FA"
    # notes + custom fields + extra URLs all stuffed into `extra`
    assert "note line 1" in row["extra"]
    assert "URL2" in row["extra"]
    assert "custom text key" in row["extra"]
    assert row["fav"] == "0"


def test_lastpass_secure_note_sentinel_for_empty_url():
    items = _synthetic()
    no_url = next(it for it in items if not it.urls)
    rows, _ = _read(write_lastpass_csv, [no_url])
    assert rows[0]["url"] == "http://sn"


# ---------- Proton Pass -----------------------------------------------------


def test_proton_columns_and_row():
    rows, headers = _read(write_proton_csv, _real())
    assert headers == [
        "type", "name", "url", "email", "username", "password",
        "note", "totp", "vault",
    ]
    row = rows[0]
    assert row["type"] == "login"
    assert row["name"] == "login display name"
    assert row["url"] == "URL1"
    # username does not contain "@" → goes into username, email stays empty
    assert row["email"] == ""
    assert row["username"] == "login username"
    assert row["password"] == "login password"
    assert "note line 1" in row["note"]
    assert "URL2" in row["note"]
    assert row["totp"] == "2FA"


def test_proton_uses_email_column_when_username_is_email():
    items = _synthetic()
    gmail = next(it for it in items if it.name == "Gmail")
    rows, _ = _read(write_proton_csv, [gmail])
    assert rows[0]["email"] == "user@example.com"
    assert rows[0]["username"] == ""


# ---------- Dashlane --------------------------------------------------------


def test_dashlane_columns_and_row():
    rows, headers = _read(write_dashlane_csv, _real())
    assert headers == [
        "username", "username2", "username3",
        "title", "password", "note", "url", "category", "otpSecret",
    ]
    row = rows[0]
    assert row["title"] == "login display name"
    assert row["username"] == "login username"
    assert row["password"] == "login password"
    assert row["url"] == "URL1"
    assert row["otpSecret"] == "2FA"
    assert "note line 1" in row["note"]
    assert "URL2" in row["note"]


# ---------- NordPass --------------------------------------------------------


def test_nordpass_columns_and_login_fields_only():
    rows, headers = _read(write_nordpass_csv, _real())
    # NordPass extended template includes lots of card/identity columns.
    for col in ("name", "url", "username", "password", "note", "folder",
                "cardnumber", "cvc", "address1", "city"):
        assert col in headers

    row = rows[0]
    assert row["name"] == "login display name"
    assert row["url"] == "URL1"
    assert row["username"] == "login username"
    assert row["password"] == "login password"
    # Card/identity columns stay empty for login items.
    assert row["cardnumber"] == ""
    assert row["address1"] == ""
    # Notes column captures notes + custom + TOTP + extra URLs.
    assert "note line 1" in row["note"]
    assert "TOTP: 2FA" in row["note"]
    assert "URL2" in row["note"]


# ---------- Apple Passwords -------------------------------------------------


def test_apple_columns_and_row():
    rows, headers = _read(write_apple_csv, _real())
    assert headers == ["Title", "URL", "Username", "Password", "Notes", "OTPAuth"]
    row = rows[0]
    assert row["Title"] == "login display name"
    assert row["URL"] == "URL1"
    assert row["Username"] == "login username"
    assert row["Password"] == "login password"
    assert "note line 1" in row["Notes"]
    assert "URL2" in row["Notes"]
    assert row["OTPAuth"].startswith("otpauth://totp/")
    assert "secret=2FA" in row["OTPAuth"]


# ---------- Chrome ----------------------------------------------------------


def test_chrome_columns_and_row():
    rows, headers = _read(write_chrome_csv, _real())
    assert headers == ["name", "url", "username", "password", "note"]
    row = rows[0]
    assert row["name"] == "login display name"
    assert row["url"] == "URL1"
    assert row["username"] == "login username"
    assert row["password"] == "login password"
    # TOTP must survive somewhere even though Chrome has no totp column.
    assert "TOTP: 2FA" in row["note"]
    assert "URL2" in row["note"]


# ---------- Firefox ---------------------------------------------------------


def test_firefox_columns_and_required_fields():
    rows, headers = _read(write_firefox_csv, _real())
    # Firefox accepts these columns and ignores everything beyond url/user/pass.
    for required in ("url", "username", "password"):
        assert required in headers
    row = rows[0]
    assert row["username"] == "login username"
    assert row["password"] == "login password"
    # URL1 has no scheme so the writer should prepend https:// for Firefox.
    assert row["url"] == "https://URL1"
    assert row["formActionOrigin"] == "https://URL1"


def test_firefox_keeps_existing_scheme():
    items = _synthetic()
    gh = next(it for it in items if it.name == "GitHub")
    rows, _ = _read(write_firefox_csv, [gh])
    assert rows[0]["url"] == "https://github.com/login"


# ---------- Sanity ----------------------------------------------------------


@pytest.mark.parametrize(
    "writer",
    [
        write_apple_csv,
        write_chrome_csv,
        write_dashlane_csv,
        write_firefox_csv,
        write_keepassxc_csv,
        write_lastpass_csv,
        write_nordpass_csv,
        write_proton_csv,
    ],
)
def test_writer_produces_one_row_per_item(writer):
    items = _synthetic()  # 4 items
    rows, _ = _read(writer, items)
    assert len(rows) == len(items)
