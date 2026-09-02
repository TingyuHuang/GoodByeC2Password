"""Parsing a C2 Password JSON export into the neutral C2Item shape.

The fixture ``tests/C2Password_Export.json`` is a real export covering every
built-in C2 type: login, contact information, payment card, wireless router
and secure note. ``fixtures/edge_cases.json`` covers what the real one
doesn't: a C2 type we don't model, nested payloads, multiple tags, and
duplicate field names.
"""

import json
from pathlib import Path

import pytest

from c2pw_convert import (
    ITEM_TYPE_CARD,
    ITEM_TYPE_IDENTITY,
    ITEM_TYPE_LOGIN,
    ITEM_TYPE_NOTE,
    parse_c2_json,
)
from c2pw_convert.parser import humanize

REAL_EXPORT = Path(__file__).parent / "C2Password_Export.json"
EDGE_CASES = Path(__file__).parent / "fixtures" / "edge_cases.json"


@pytest.fixture
def items():
    return parse_c2_json(REAL_EXPORT)


def _named(items, fragment):
    return next(i for i in items if fragment in i.name)


# ---- Item types ------------------------------------------------------------


def test_every_builtin_c2_type_is_recognized(items):
    assert [i.item_type for i in items] == [
        ITEM_TYPE_LOGIN,
        ITEM_TYPE_IDENTITY,   # contact information
        ITEM_TYPE_CARD,
        ITEM_TYPE_NOTE,       # wireless router, already a note in the export
        ITEM_TYPE_NOTE,
    ]


def test_login_payload(items):
    login = _named(items, "login type item")
    assert login.username == "username value"
    assert login.password == "password value"
    assert login.totp == "2AactorAuthentication"
    assert login.urls == ["http://example.com"]
    assert login.notes == "notes value"


def test_identity_payload_keeps_bitwarden_key_names(items):
    identity = _named(items, "Contact information").identity
    assert identity["firstName"] == "First name"
    assert identity["postalCode"] == "ZIP code"
    assert identity["country"] == "TW"
    assert identity["phone"] == "+886987654321"


def test_card_payload(items):
    card = _named(items, "payment card").card
    assert card["number"] == "4242 4242 4242 4242"
    assert card["brand"] == "Visa"
    assert card["code"] == "456"


# ---- Requirement: custom fields stay custom fields -------------------------


def test_custom_fields_are_kept_one_per_value(items):
    login = _named(items, "login type item")
    assert login.custom_fields == {
        "Custom Field - Text Key": "text value",
        "Custom Field - Password Key": "password value",
        "Custom Field - 2-factor authentication": "2FAvalue",
        "Custom Field - Address": (
            "ZIP code TWState/ProvinceCounty/DistrictCity/TownAddress"
        ),
    }


def test_hidden_fields_are_flagged(items):
    login = _named(items, "login type item")
    assert login.sensitive_fields == {
        "Custom Field - Password Key",
        "Custom Field - 2-factor authentication",
    }


def test_router_attributes_each_get_their_own_field(items):
    """A C2 type Bitwarden lacks arrives itemized, and must stay that way."""
    router = _named(items, "wireless router")
    assert router.item_type == ITEM_TYPE_NOTE
    assert router.custom_fields == {
        "Router Name": "network name (ssid)",
        "Router Password": "password",
        "Router Security": "wpa3-personal",
        "Router IP": "ip address",
        "Router Admin Username": "admin username",
        "Router Admin Password": "admin password",
    }
    assert router.sensitive_fields == {"Router Password", "Router Admin Password"}


# ---- Tags ------------------------------------------------------------------


def test_tags_field_is_lifted_out_of_custom_fields(items):
    for item in items:
        assert "Tags" not in item.custom_fields
    assert [i.tag for i in items] == ["tag a", "tag b", "tag b", "tag b", "tag c"]


def test_multiple_tags_keep_the_full_value_as_a_field():
    """Bitwarden allows one folder, so the rest must survive somewhere."""
    item = parse_c2_json(EDGE_CASES)[0]
    assert item.tag == "alpha"
    assert item.custom_fields["Tags"] == "alpha\nbeta"


# ---- Unknown types ---------------------------------------------------------


def test_unknown_c2_type_becomes_a_note_with_itemized_fields():
    item = parse_c2_json(EDGE_CASES)[0]
    assert item.item_type == ITEM_TYPE_NOTE
    assert item.custom_fields["Bank Account Bank Name"] == "Some Bank"
    # Nested objects and arrays are walked, never dumped as JSON.
    assert item.custom_fields["Bank Account Routing Code"] == "0001"
    assert item.custom_fields["Bank Account Routing Branch"] == "Main"
    assert item.custom_fields["Bank Account Holders 1"] == "A"
    assert item.custom_fields["Bank Account Holders 2"] == "B"
    assert not any("{" in v for v in item.custom_fields.values())


def test_unmodelled_key_in_a_typed_payload_becomes_a_field():
    item = parse_c2_json(EDGE_CASES)[1]
    assert "issuingCountry" not in item.card
    assert item.custom_fields["Card Issuing Country"] == "TW"


def test_duplicate_field_names_do_not_clobber_each_other():
    item = parse_c2_json(EDGE_CASES)[3]
    assert item.custom_fields["Code"] == "first"
    assert item.custom_fields["Code (2)"] == "second"
    assert "Code (2)" in item.sensitive_fields


# ---- Input handling --------------------------------------------------------


def test_accepts_bytes_with_a_bom():
    raw = REAL_EXPORT.read_bytes()
    assert len(parse_c2_json(b"\xef\xbb\xbf" + raw)) == 5


def test_accepts_a_bare_array_of_items():
    payload = json.loads(REAL_EXPORT.read_text(encoding="utf-8-sig"))
    assert len(parse_c2_json(json.dumps(payload["items"]))) == 5


def test_accepts_json_text_longer_than_the_filename_limit():
    """Regression: text input used to be probed against the filesystem.

    ``Path(text).exists()`` asks the OS to stat a filename the size of the
    whole export. Python 3.14's pathlib suppresses the ENAMETOOLONG; 3.10-3.13
    raise it, so passing decoded JSON crashed everywhere but the newest
    interpreter.
    """
    text = REAL_EXPORT.read_text(encoding="utf-8-sig")
    assert len(text) > 255  # comfortably past NAME_MAX
    assert len(parse_c2_json(text)) == 5


def test_accepts_a_path_given_as_a_plain_string():
    assert len(parse_c2_json(str(REAL_EXPORT))) == 5


def test_accepts_a_path_object():
    assert len(parse_c2_json(REAL_EXPORT)) == 5


def test_rejects_json_that_is_not_a_c2_export():
    with pytest.raises(ValueError, match="Not a C2 Password JSON export"):
        parse_c2_json('{"vault": []}')


def test_humanize_splits_camel_case():
    assert humanize("cardholderName") == "Cardholder Name"
    assert humanize("postalCode") == "Postal Code"
    assert humanize("title") == "Title"


# ---- Nothing may be silently dropped ---------------------------------------


def test_every_value_in_the_export_reaches_some_c2item_attribute(items):
    """Walk the raw JSON and assert each leaf value shows up somewhere."""
    raw = json.loads(REAL_EXPORT.read_text(encoding="utf-8-sig"))

    landed = set()
    for it in items:
        landed.update(
            [it.name, it.notes, it.tag, it.username, it.password, it.totp]
        )
        landed.update(it.urls)
        landed.update(it.card.values())
        landed.update(it.identity.values())
        landed.update(it.custom_fields.values())
        # Field *names* have to survive too, as custom-field keys.
        landed.update(it.custom_fields.keys())

    # "Tags" is the one name deliberately consumed: it becomes item.tag.
    landed.add("Tags")

    def leaves(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in {"type", "match", "favorite"}:
                    continue
                yield from leaves(v)
        elif isinstance(node, list):
            for v in node:
                yield from leaves(v)
        elif isinstance(node, str) and node:
            yield node

    for value in leaves(raw):
        assert value in landed, f"{value!r} was dropped"
