"""The Bitwarden JSON writer — the one lossless target.

Two rules from the spec are load-bearing here and each has its own test:

1. A C2 custom field becomes a Bitwarden custom field (hidden if C2 marked
   it hidden), not a line of text in the notes.
2. A C2 type Bitwarden has no cipher for becomes a Secure Note whose every
   attribute is its own custom field — never a JSON blob in one field.
"""

import io
import json
from pathlib import Path

import pytest

from c2pw_convert import build_bitwarden_export, parse_c2_json, write_bitwarden_json
from c2pw_convert.bitwarden_json import (
    CIPHER_TYPE_CARD,
    CIPHER_TYPE_IDENTITY,
    CIPHER_TYPE_LOGIN,
    CIPHER_TYPE_SECURE_NOTE,
    FIELD_TYPE_HIDDEN,
    FIELD_TYPE_TEXT,
)

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.json"
EDGE_CASES = Path(__file__).parent / "fixtures" / "edge_cases.json"


@pytest.fixture
def export():
    return build_bitwarden_export(parse_c2_json(REAL_EXPORT))


def _by_name(export, fragment):
    return next(i for i in export["items"] if fragment in i["name"])


def _fields(cipher):
    return {f["name"]: f for f in cipher["fields"]}


# ---- Cipher types ----------------------------------------------------------


def test_each_c2_type_maps_to_its_real_cipher_type(export):
    assert [i["type"] for i in export["items"]] == [
        CIPHER_TYPE_LOGIN,
        CIPHER_TYPE_IDENTITY,   # contact information
        CIPHER_TYPE_CARD,
        CIPHER_TYPE_SECURE_NOTE,
        CIPHER_TYPE_SECURE_NOTE,
    ]


def test_login_cipher(export):
    login = _by_name(export, "login type item")["login"]
    assert login["username"] == "username value"
    assert login["password"] == "password value"
    assert login["totp"] == "2AactorAuthentication"
    assert login["uris"] == [{"match": None, "uri": "http://example.com"}]


def test_identity_cipher_keeps_every_key(export):
    identity = _by_name(export, "Contact information")["identity"]
    assert identity["title"] == "Mr"
    assert identity["firstName"] == "First name"
    assert identity["postalCode"] == "ZIP code"
    assert identity["email"] == "tingyuh@example.com"


def test_card_cipher(export):
    card = _by_name(export, "payment card")["card"]
    assert card["cardholderName"] == "cardholder name"
    assert card["brand"] == "Visa"
    assert card["number"] == "4242 4242 4242 4242"
    assert card["code"] == "456"


def test_card_expiry_is_normalized_for_bitwardens_form(export):
    """C2 writes 01/23; Bitwarden matches an unpadded month and a 4-digit year."""
    card = _by_name(export, "payment card")["card"]
    assert card["expMonth"] == "1"
    assert card["expYear"] == "2023"


# ---- Requirement 1: custom fields become custom fields ---------------------


def test_custom_fields_become_bitwarden_custom_fields(export):
    fields = _fields(_by_name(export, "login type item"))
    assert fields["Custom Field - Text Key"]["value"] == "text value"
    assert fields["Custom Field - Password Key"]["value"] == "password value"
    assert fields["Custom Field - Address"]["value"].startswith("ZIP code")


def test_hidden_custom_fields_stay_hidden(export):
    fields = _fields(_by_name(export, "login type item"))
    assert fields["Custom Field - Password Key"]["type"] == FIELD_TYPE_HIDDEN
    assert fields["Custom Field - 2-factor authentication"]["type"] == FIELD_TYPE_HIDDEN
    assert fields["Custom Field - Text Key"]["type"] == FIELD_TYPE_TEXT


def test_custom_fields_ride_along_with_typed_ciphers(export):
    """A Card cipher still carries the fields Bitwarden's Card can't model."""
    fields = _fields(_by_name(export, "payment card"))
    assert fields["Card PIN"]["value"] == "PIN code"
    assert fields["Card PIN"]["type"] == FIELD_TYPE_HIDDEN
    assert fields["Card URL"]["value"] == "bank website"

    identity_fields = _fields(_by_name(export, "Contact information"))
    assert identity_fields["Contact Birthday"]["value"] == "2026-09-02T00:00:00"
    assert identity_fields["Contact Job"]["value"] == "Job title"


# ---- Requirement 2: unsupported types itemize, never serialize -------------


def test_router_becomes_a_note_with_one_field_per_attribute(export):
    router = _by_name(export, "wireless router")
    assert router["type"] == CIPHER_TYPE_SECURE_NOTE
    assert router["secureNote"] == {"type": 0}

    fields = _fields(router)
    assert fields["Router Name"]["value"] == "network name (ssid)"
    assert fields["Router Security"]["value"] == "wpa3-personal"
    assert fields["Router IP"]["value"] == "ip address"
    assert fields["Router Password"]["type"] == FIELD_TYPE_HIDDEN
    assert fields["Router Admin Password"]["type"] == FIELD_TYPE_HIDDEN


def test_unknown_c2_type_is_itemized_not_serialized():
    export = build_bitwarden_export(parse_c2_json(EDGE_CASES))
    cipher = _by_name(export, "unknown C2 type")
    assert cipher["type"] == CIPHER_TYPE_SECURE_NOTE

    fields = _fields(cipher)
    assert fields["Bank Account Bank Name"]["value"] == "Some Bank"
    assert fields["Bank Account Routing Code"]["value"] == "0001"
    assert fields["Bank Account Holders 2"]["value"] == "B"
    # The whole point: no value is a serialized structure.
    for f in cipher["fields"]:
        assert not f["value"].lstrip().startswith(("{", "["))


def test_no_cipher_anywhere_hides_a_payload_inside_one_value(export):
    for cipher in export["items"]:
        for f in cipher["fields"]:
            assert not f["value"].lstrip().startswith(("{", "["))


# ---- Folders ---------------------------------------------------------------


def test_tags_become_folders_that_items_point_at(export):
    assert sorted(f["name"] for f in export["folders"]) == ["tag a", "tag b", "tag c"]
    by_name = {f["name"]: f["id"] for f in export["folders"]}
    assert _by_name(export, "login type item")["folderId"] == by_name["tag a"]
    assert _by_name(export, "payment card")["folderId"] == by_name["tag b"]


def test_tags_are_not_also_left_as_a_custom_field(export):
    for cipher in export["items"]:
        assert "Tags" not in _fields(cipher)


# ---- Output shape ----------------------------------------------------------


def test_output_is_stable_across_runs():
    first, second = io.StringIO(), io.StringIO()
    write_bitwarden_json(parse_c2_json(REAL_EXPORT), first)
    write_bitwarden_json(parse_c2_json(REAL_EXPORT), second)
    assert first.getvalue() == second.getvalue()
    assert json.loads(first.getvalue())["encrypted"] is False


def test_ids_are_unique(export):
    ids = [i["id"] for i in export["items"]]
    assert len(ids) == len(set(ids))
