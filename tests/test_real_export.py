"""Round-trip tests against a real Synology C2 Password export.

The fixture ``tests/C2Password_Export.csv`` is a one-row export captured
from the real product. It exercises the things the synthetic fixture
doesn't: header column ordering different from our canonical list,
multi-line ``Login_URLs`` / ``Login_URL_Match_Rules`` / ``Notes`` cells,
and a JSON-encoded ``Others`` field with all four C2 custom-field types
(Text, Password, TOTP, Address).
"""

import csv
import io
from pathlib import Path

from c2pw_convert import parse_c2_csv, write_bitwarden_csv, write_onepassword_csv

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.csv"


def _items():
    return parse_c2_csv(REAL_EXPORT)


def test_real_export_parses_one_login_row():
    items = _items()
    assert len(items) == 1


def test_real_export_top_level_fields():
    item = _items()[0]
    assert item.name == "login display name"
    assert item.username == "login username"
    assert item.password == "login password"
    assert item.totp == "2FA"
    assert item.tag == ""
    assert item.tag_color == ""
    assert item.favorite is False


def test_real_export_multiline_urls_and_match_rules():
    item = _items()[0]
    # Both columns use embedded newlines inside one quoted CSV cell.
    assert item.urls == ["URL1", "URL2"]
    assert item.url_match_rules == ["tld-plus-one", "tld-plus-one"]


def test_real_export_multiline_notes_preserved():
    item = _items()[0]
    assert item.notes == "note line 1\nnote line 2\nnote line 3"


def test_real_export_others_json_is_flattened():
    """The ``Others`` cell is a JSON object describing typed custom fields."""
    custom = _items()[0].custom_fields

    # Title trailing whitespace is trimmed.
    assert custom["custom text key"] == "custom text value"
    assert custom["custom password key"] == "custom password value"
    assert custom["custom 2FA key"] == "custom2favalue"

    # Address gets formatted as multi-line text (street / locality / location).
    address = custom["custom address key"]
    assert "custon address value" in address
    assert "city/town" in address
    assert "country/district" in address
    assert "state/province" in address
    assert "zip code" in address
    assert address.endswith("TW")


def test_real_export_to_bitwarden_csv():
    items = _items()
    buf = io.StringIO()
    write_bitwarden_csv(items, buf)
    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert len(rows) == 1

    row = rows[0]
    assert row["type"] == "login"
    assert row["name"] == "login display name"
    assert row["login_username"] == "login username"
    assert row["login_password"] == "login password"
    assert row["login_totp"] == "2FA"
    assert row["login_uri"] == "URL1,URL2"
    assert row["notes"] == "note line 1\nnote line 2\nnote line 3"
    assert row["folder"] == ""
    assert row["favorite"] == ""
    assert row["reprompt"] == "0"

    # Custom fields packed into Bitwarden's `fields` column as `name: value`.
    fields = row["fields"]
    assert "custom text key: custom text value" in fields
    assert "custom password key: custom password value" in fields
    assert "custom 2FA key: custom2favalue" in fields
    assert "custom address key:" in fields


def test_real_export_to_onepassword_csv():
    items = _items()
    buf = io.StringIO()
    write_onepassword_csv(items, buf)
    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert len(rows) == 1

    row = rows[0]
    assert row["Title"] == "login display name"
    assert row["Username"] == "login username"
    assert row["Password"] == "login password"
    # The first URL goes into Url; the second is preserved in Additional URLs.
    assert row["Url"] == "URL1"
    assert row["Additional URLs"] == "URL2"
    # Bare TOTP secret is wrapped into an otpauth URI.
    assert row["OTPAuth"].startswith("otpauth://totp/")
    assert "secret=2FA" in row["OTPAuth"]
    assert row["Notes"] == "note line 1\nnote line 2\nnote line 3"

    # Custom fields appear as their own columns named after the title.
    assert row["custom text key"] == "custom text value"
    assert row["custom password key"] == "custom password value"
    assert row["custom 2FA key"] == "custom2favalue"
    assert "custon address value" in row["custom address key"]


def test_real_export_no_extra_or_missing_data():
    """Sanity: every C2 field in the source row reaches at least one output."""
    items = _items()
    buf = io.StringIO()
    write_bitwarden_csv(items, buf)
    bw = buf.getvalue()

    expected_fragments = [
        "login display name",
        "login username",
        "login password",
        "URL1",
        "URL2",
        "note line 1",
        "note line 2",
        "note line 3",
        "custom text key",
        "custom text value",
        "custom password key",
        "custom password value",
        "custom 2FA key",
        "custom2favalue",
        "custom address key",
        "custon address value",
        "city/town",
    ]
    for frag in expected_fragments:
        assert frag in bw, f"missing {frag!r} from Bitwarden output"
