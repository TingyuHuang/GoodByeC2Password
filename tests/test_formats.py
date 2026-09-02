"""The nine CSV writers.

None of these formats has a typed card, identity, or custom-field concept, so
every value that isn't a login credential has to be written out into the notes
column — one ``Label: value`` line per value, never a packed blob. That rule is
what most of these tests check.
"""

import csv
import io
from pathlib import Path

import pytest

from c2pw_convert import (
    parse_c2_json,
    write_apple_csv,
    write_chrome_csv,
    write_dashlane_csv,
    write_firefox_csv,
    write_keepassxc_csv,
    write_lastpass_csv,
    write_nordpass_csv,
    write_proton_csv,
)

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.json"

ALL_WRITERS = [
    write_apple_csv,
    write_chrome_csv,
    write_dashlane_csv,
    write_firefox_csv,
    write_keepassxc_csv,
    write_lastpass_csv,
    write_nordpass_csv,
    write_proton_csv,
]


@pytest.fixture
def items():
    return parse_c2_json(REAL_EXPORT)


def _rows(writer, items):
    buf = io.StringIO()
    writer(items, buf)
    buf.seek(0)
    return list(csv.DictReader(buf))


def _named(rows, key, fragment):
    return next(r for r in rows if fragment in r[key])


# ---- Login mapping ---------------------------------------------------------


def test_keepassxc_login_row(items):
    row = _named(_rows(write_keepassxc_csv, items), "Title", "login type item")
    assert row["Username"] == "username value"
    assert row["Password"] == "password value"
    assert row["URL"] == "http://example.com"
    assert row["Group"] == "tag a"
    assert row["TOTP"].startswith("otpauth://totp/")


def test_lastpass_uses_its_secure_note_sentinel_url(items):
    row = _named(_rows(write_lastpass_csv, items), "name", "Secure note")
    assert row["url"] == "http://sn"


def test_proton_marks_non_logins_as_notes(items):
    rows = _rows(write_proton_csv, items)
    assert [r["type"] for r in rows] == ["login", "note", "note", "note", "note"]


def test_proton_routes_email_like_usernames_to_the_email_column(items):
    rows = _rows(write_proton_csv, items)
    login = _named(rows, "name", "login type item")
    # "username value" has no @, so it stays a username.
    assert login["username"] == "username value"
    assert login["email"] == ""


def test_dashlane_keeps_the_totp_secret_raw(items):
    row = _named(_rows(write_dashlane_csv, items), "title", "login type item")
    assert row["otpSecret"] == "2AactorAuthentication"


def test_apple_wraps_totp_as_an_otpauth_uri(items):
    row = _named(_rows(write_apple_csv, items), "Title", "login type item")
    assert row["OTPAuth"].startswith("otpauth://totp/")
    assert "2AactorAuthentication" in row["OTPAuth"]


# ---- Typed payloads have to be itemized, not packed ------------------------


def test_card_values_are_listed_one_per_line(items):
    row = _named(_rows(write_keepassxc_csv, items), "Title", "payment card")
    notes = row["Notes"]
    assert "Cardholder Name: cardholder name" in notes
    assert "Number: 4242 4242 4242 4242" in notes
    assert "Code: 456" in notes
    # ...and not as a serialized object.
    assert "{" not in notes


def test_identity_values_are_listed_one_per_line(items):
    row = _named(_rows(write_keepassxc_csv, items), "Title", "Contact information")
    notes = row["Notes"]
    assert "First Name: First name" in notes
    assert "Postal Code: ZIP code" in notes
    assert "Phone: +886987654321" in notes
    assert "{" not in notes


def test_custom_fields_are_listed_one_per_line(items):
    row = _named(_rows(write_keepassxc_csv, items), "Title", "wireless router")
    notes = row["Notes"]
    for line in [
        "Router Name: network name (ssid)",
        "Router Password: password",
        "Router Admin Username: admin username",
    ]:
        assert line in notes


def test_non_login_notes_carry_a_type_stamp(items):
    row = _named(_rows(write_keepassxc_csv, items), "Title", "payment card")
    assert row["Notes"].startswith("C2 item type: Payment card")


def test_login_notes_have_no_type_stamp(items):
    row = _named(_rows(write_keepassxc_csv, items), "Title", "login type item")
    assert not row["Notes"].startswith("C2 item type:")


# ---- NordPass has real card columns ----------------------------------------


def test_nordpass_card_uses_its_dedicated_columns(items):
    row = _named(_rows(write_nordpass_csv, items), "name", "payment card")
    assert row["cardholdername"] == "cardholder name"
    assert row["cardnumber"] == "4242 4242 4242 4242"
    assert row["cvc"] == "456"
    assert row["expirydate"] == "01/23"
    # Mapped values must not be repeated in the note.
    assert "4242 4242 4242 4242" not in row["note"]
    # Unmapped ones still have to survive.
    assert "Brand: Visa" in row["note"]
    assert "Card PIN: PIN code" in row["note"]


def test_nordpass_moves_totp_into_the_note(items):
    row = _named(_rows(write_nordpass_csv, items), "name", "login type item")
    assert "TOTP: 2AactorAuthentication" in row["note"]


# ---- Login-only formats ----------------------------------------------------


@pytest.mark.parametrize("writer", [write_chrome_csv, write_firefox_csv])
def test_login_only_formats_skip_everything_else(writer, items):
    rows = _rows(writer, items)
    assert len(rows) == 1


def test_firefox_adds_a_scheme_to_bare_hosts():
    from c2pw_convert.parser import C2Item

    rows = _rows(write_firefox_csv, [C2Item(name="x", urls=["example.com"])])
    assert rows[0]["url"] == "https://example.com"


# ---- Every writer must survive every item type -----------------------------


@pytest.mark.parametrize("writer", ALL_WRITERS)
def test_writer_handles_all_item_types_without_raising(writer, items):
    buf = io.StringIO()
    writer(items, buf)
    assert buf.getvalue().splitlines()[0]  # header row present
