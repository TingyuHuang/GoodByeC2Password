import csv
import io
from pathlib import Path

from c2pw_convert import parse_c2_csv, write_bitwarden_csv, write_onepassword_csv

FIXTURE = Path(__file__).parent / "fixtures" / "sample_c2.csv"


def test_parse_basic_fields():
    items = parse_c2_csv(FIXTURE)
    assert len(items) == 4

    github = items[0]
    assert github.name == "GitHub"
    assert github.urls == ["https://github.com/login", "https://github.com"]
    assert github.username == "octocat"
    assert github.password == "hunter2!@#"
    assert github.totp == "JBSWY3DPEHPK3PXP"
    assert github.tag == "Dev"
    assert github.favorite is True
    assert "Two-factor enabled" in github.notes
    assert github.custom_fields["Account ID"] == "12345"
    assert "Security questions" in " ".join(github.custom_fields.keys())


def test_parse_handles_nullish_and_missing():
    items = parse_c2_csv(FIXTURE)
    no_url = items[2]
    assert no_url.name == "NoURL Item"
    assert no_url.urls == []
    assert no_url.favorite is False

    empty_totp = items[3]
    # "nan" must be normalized to empty
    assert empty_totp.totp == ""
    assert empty_totp.favorite is False


def test_bitwarden_output_columns_and_rows():
    items = parse_c2_csv(FIXTURE)
    buf = io.StringIO()
    write_bitwarden_csv(items, buf)
    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert len(rows) == 4

    gh = rows[0]
    assert gh["type"] == "login"
    assert gh["name"] == "GitHub"
    assert gh["folder"] == "Dev"
    assert gh["favorite"] == "1"
    assert gh["login_uri"] == "https://github.com/login,https://github.com"
    assert gh["login_username"] == "octocat"
    assert gh["login_password"] == "hunter2!@#"
    assert gh["login_totp"] == "JBSWY3DPEHPK3PXP"
    assert gh["reprompt"] == "0"
    assert "Account ID: 12345" in gh["fields"]


def test_onepassword_output_includes_otpauth_and_extra_urls():
    items = parse_c2_csv(FIXTURE)
    buf = io.StringIO()
    write_onepassword_csv(items, buf)
    buf.seek(0)
    rows = list(csv.DictReader(buf))
    assert len(rows) == 4

    gh = rows[0]
    assert gh["Title"] == "GitHub"
    assert gh["Url"] == "https://github.com/login"
    assert gh["Username"] == "octocat"
    assert gh["Password"] == "hunter2!@#"
    assert gh["OTPAuth"].startswith("otpauth://totp/")
    assert "secret=JBSWY3DPEHPK3PXP" in gh["OTPAuth"]
    assert gh["Favorite"] == "Y"
    assert gh["Tags"] == "Dev"
    assert gh["Additional URLs"] == "https://github.com"

    gmail = rows[1]
    # No TOTP -> empty OTPAuth, not a malformed URI
    assert gmail["OTPAuth"] == ""
    assert gmail["Favorite"] == ""


def test_password_with_special_chars_roundtrip():
    items = parse_c2_csv(FIXTURE)
    gmail = items[1]
    assert gmail.password == "p@ss w/ space"

    buf = io.StringIO()
    write_bitwarden_csv(items, buf)
    buf.seek(0)
    parsed = list(csv.DictReader(buf))
    assert parsed[1]["login_password"] == "p@ss w/ space"


def test_parse_from_bytes_with_bom():
    raw = FIXTURE.read_bytes()
    bom_data = b"\xef\xbb\xbf" + raw
    items = parse_c2_csv(bom_data)
    assert items[0].name == "GitHub"


def test_unrecognized_headers_raise():
    bad = "foo,bar\n1,2\n"
    try:
        parse_c2_csv(bad.encode("utf-8"))
    except ValueError as exc:
        assert "Could not recognize" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown headers")
