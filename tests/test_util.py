"""Tests for shared helpers in c2pw_convert._util.

The interesting cases are around otpauth URI construction: Base32 secrets
often have trailing ``=`` padding that used to get pasted straight into the
query string, and callers may already hand us a fully-formed otpauth URI
that must round-trip unchanged.
"""

from urllib.parse import parse_qs, urlsplit

from c2pw_convert._util import otpauth_uri


def _query(uri: str) -> dict:
    """Parse an otpauth URI's query string. Uses strict parsing so an
    unencoded '=' inside a value would split it into two keys and this
    would fail loudly."""
    return parse_qs(urlsplit(uri).query, strict_parsing=True, keep_blank_values=True)


def test_empty_secret_yields_empty_string():
    assert otpauth_uri("", "user", "issuer") == ""


def test_passthrough_when_secret_already_is_otpauth_uri():
    already = "otpauth://totp/Example?secret=ABCDEFGH&issuer=Example"
    assert otpauth_uri(already, "ignored", "ignored") == already


def test_base32_padding_is_percent_encoded():
    """A padded Base32 secret must not leak an unescaped '=' into the query."""
    uri = otpauth_uri("JBSWY3DPEHPK3PXP=", "octocat", "GitHub")
    # Query must parse without ambiguity, and the secret must be the raw
    # (unpadded when decoded) value.
    q = _query(uri)
    assert q["secret"] == ["JBSWY3DPEHPK3PXP="]
    assert q["issuer"] == ["GitHub"]
    # And on the wire the '=' must be percent-encoded.
    assert "secret=JBSWY3DPEHPK3PXP%3D" in uri


def test_ampersand_in_secret_is_percent_encoded():
    """Non-Base32 secrets can contain '&' too — must not create a new pair."""
    uri = otpauth_uri("a&b=c", "u", "i")
    q = _query(uri)
    assert q["secret"] == ["a&b=c"]
    # Whatever pairs exist, none of them should be the injected 'b'.
    assert "b" not in q


def test_label_uses_issuer_colon_account():
    uri = otpauth_uri("SECRET", "octocat", "GitHub")
    path = urlsplit(uri).path
    # path is "/GitHub%3Aoctocat" or "/GitHub:octocat" — both acceptable.
    assert path.lstrip("/") in ("GitHub:octocat", "GitHub%3Aoctocat")


def test_falls_back_to_issuer_or_account_when_only_one_given():
    assert otpauth_uri("S", "", "GitHub").startswith("otpauth://totp/GitHub?")
    assert otpauth_uri("S", "octocat", "").startswith("otpauth://totp/octocat?")


def test_falls_back_to_c2_label_when_both_empty():
    assert otpauth_uri("S", "", "").startswith("otpauth://totp/C2?")
