"""Parser for Synology C2 Password JSON exports.

A C2 export looks like::

    {"items": [
      {"name": "...", "notes": "...", "favorite": false,
       "fields": [{"type": 0, "name": "Tags", "value": "tag a"},
                  {"type": 1, "name": "Custom Field - Password Key", ...}],
       "type": 1,
       "login": {"username": "...", "password": "...", "totp": "...",
                 "uris": [{"uri": "...", "match": null}]}}
    ]}

``type`` follows Bitwarden's cipher numbering — 1 Login, 2 Secure Note,
3 Card, 4 Identity — and the payload sits in a matching ``login`` /
``secureNote`` / ``card`` / ``identity`` object.

C2 item types with no Bitwarden equivalent (a wireless router, say) are
already exported as Secure Notes whose every attribute is one entry in
``fields``. We keep that shape: a value never gets packed into another
value as JSON or as a joined string.

Two things do get lifted out of ``fields``:

* ``Tags`` becomes :attr:`C2Item.tag`, which downstream turns into a real
  Bitwarden folder rather than staying a text field.
* ``fields[].type == 1`` marks a secret, recorded in
  :attr:`C2Item.sensitive_fields` so writers that can hide a field do.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp1252", "iso-8859-1")

# ---- Item types -----------------------------------------------------------

ITEM_TYPE_LOGIN = "login"
ITEM_TYPE_NOTE = "note"
ITEM_TYPE_CARD = "card"
ITEM_TYPE_IDENTITY = "identity"

# C2's numeric type -> ours. Anything else degrades to a note (see
# _payload_for_unknown_type) so an unfamiliar C2 type still round-trips.
C2_TYPE_TO_ITEM_TYPE = {
    1: ITEM_TYPE_LOGIN,
    2: ITEM_TYPE_NOTE,
    3: ITEM_TYPE_CARD,
    4: ITEM_TYPE_IDENTITY,
}

ITEM_TYPE_DISPLAY = {
    ITEM_TYPE_LOGIN: "Login",
    ITEM_TYPE_NOTE: "Secure note",
    ITEM_TYPE_CARD: "Payment card",
    ITEM_TYPE_IDENTITY: "Contact information",
}

#: The ``fields`` entry C2 uses for tags; lifted into :attr:`C2Item.tag`.
TAG_FIELD_NAME = "Tags"

FIELD_TYPE_HIDDEN = 1

# Keys we copy verbatim into C2Item.card / C2Item.identity. Anything else in
# those objects becomes a custom field rather than being dropped.
CARD_KEYS = ("cardholderName", "brand", "number", "expMonth", "expYear", "code")
IDENTITY_KEYS = (
    "title", "firstName", "middleName", "lastName",
    "address1", "address2", "address3",
    "city", "state", "postalCode", "country",
    "company", "email", "phone",
    "ssn", "username", "passportNumber", "licenseNumber",
)

# Top-level item keys that have a home of their own.
_ITEM_META_KEYS = {
    "name", "notes", "favorite", "fields", "type",
    "login", "secureNote", "card", "identity",
    # Present in some exports, carrying no data we can use.
    "id", "organizationId", "folderId", "collectionIds", "reprompt",
    "passwordHistory", "revisionDate", "creationDate", "deletedDate",
}

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@dataclass
class C2Item:
    """One item from a C2 Password export, in a vendor-neutral shape."""

    name: str = ""
    item_type: str = ITEM_TYPE_LOGIN
    notes: str = ""
    favorite: bool = False
    tag: str = ""

    # Login payload.
    urls: list[str] = field(default_factory=list)
    username: str = ""
    password: str = ""
    totp: str = ""

    # Typed payloads, keyed as Bitwarden names them.
    card: dict[str, str] = field(default_factory=dict)
    identity: dict[str, str] = field(default_factory=dict)

    #: Every remaining attribute, one entry per value — never a packed blob.
    custom_fields: dict[str, str] = field(default_factory=dict)
    #: Keys of ``custom_fields`` holding secrets; writers that support a
    #: hidden field use this, plain-CSV targets ignore it.
    sensitive_fields: set[str] = field(default_factory=set)


def humanize(key: str) -> str:
    """``cardholderName`` -> ``Cardholder Name``; ``address1`` -> ``Address1``."""
    spaced = _CAMEL_BOUNDARY.sub(" ", key)
    return spaced[:1].upper() + spaced[1:]


def _decode(data: bytes) -> str:
    last_err: Exception | None = None
    for enc in ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError as exc:
            last_err = exc
    raise UnicodeDecodeError(
        "c2pw", data, 0, len(data), f"none of {ENCODINGS} worked: {last_err}"
    )


def _text(value: Any) -> str:
    """Scalar -> string. Never used on containers; those get flattened."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _flatten(value: Any, label: str, into: dict[str, str]) -> None:
    """Record ``value`` under ``label``, one entry per scalar.

    Nested objects and arrays are walked so that every leaf gets its own
    entry — a payload is never stuffed into a single field as JSON.
    """
    if isinstance(value, dict):
        for key, sub in value.items():
            _flatten(sub, f"{label} {humanize(str(key))}".strip(), into)
        return
    if isinstance(value, list):
        for idx, sub in enumerate(value, start=1):
            _flatten(sub, f"{label} {idx}", into)
        return
    text = _text(value)
    if text:
        into[_unique_key(label, into)] = text


def _unique_key(label: str, existing: dict[str, str]) -> str:
    if label not in existing:
        return label
    n = 2
    while f"{label} ({n})" in existing:
        n += 1
    return f"{label} ({n})"


def _read_fields(raw: Any, item: C2Item) -> None:
    """Copy the ``fields`` array into custom fields, lifting out Tags."""
    if not isinstance(raw, list):
        return
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        value = entry.get("value")
        if name == TAG_FIELD_NAME:
            item.tag = _tag_from(_text(value), item)
            continue
        if not name:
            name = "Field"
        # A field's value should be a scalar, but flatten defensively so an
        # unexpected object still lands as separate entries.
        if isinstance(value, (dict, list)):
            _flatten(value, name, item.custom_fields)
            continue
        text = _text(value)
        if not text:
            continue
        key = _unique_key(name, item.custom_fields)
        item.custom_fields[key] = text
        if entry.get("type") == FIELD_TYPE_HIDDEN:
            item.sensitive_fields.add(key)


def _tag_from(value: str, item: C2Item) -> str:
    """A Bitwarden item belongs to exactly one folder.

    C2 allows several tags. We use the first as the folder name and keep the
    untouched original as a field so the rest is not lost.
    """
    parts = [p.strip() for p in value.replace("\r\n", "\n").split("\n") if p.strip()]
    if len(parts) > 1:
        item.custom_fields[TAG_FIELD_NAME] = value.strip()
    return parts[0] if parts else ""


def _read_login(raw: Any, item: C2Item) -> None:
    if not isinstance(raw, dict):
        return
    item.username = _text(raw.get("username"))
    item.password = _text(raw.get("password"))
    item.totp = _text(raw.get("totp"))
    uris = raw.get("uris")
    if isinstance(uris, list):
        for entry in uris:
            uri = entry.get("uri") if isinstance(entry, dict) else entry
            text = _text(uri).strip()
            if text:
                item.urls.append(text)


def _read_typed(raw: Any, keys: Iterable[str], item: C2Item, label: str) -> dict[str, str]:
    """Pull known keys into a typed dict; flatten the leftovers into fields."""
    if not isinstance(raw, dict):
        return {}
    known = set(keys)
    typed = {k: _text(raw.get(k)) for k in keys if _text(raw.get(k))}
    for key, value in raw.items():
        if key in known:
            continue
        _flatten(value, f"{label} {humanize(str(key))}".strip(), item.custom_fields)
    return typed


def _payload_for_unknown_type(raw: dict[str, Any], item: C2Item) -> None:
    """A C2 type we don't model becomes a note with itemized fields.

    Every payload key gets its own custom field. Nothing is serialized into
    another field as JSON, which is the whole point of the note fallback.
    """
    for key, value in raw.items():
        if key in _ITEM_META_KEYS:
            continue
        _flatten(value, humanize(str(key)), item.custom_fields)


def _item_from(raw: dict[str, Any]) -> C2Item:
    item = C2Item(
        name=_text(raw.get("name")).strip(),
        notes=_text(raw.get("notes")),
        favorite=bool(raw.get("favorite")),
    )
    _read_fields(raw.get("fields"), item)

    item.item_type = C2_TYPE_TO_ITEM_TYPE.get(raw.get("type"), ITEM_TYPE_NOTE)

    if item.item_type == ITEM_TYPE_LOGIN:
        _read_login(raw.get("login"), item)
    elif item.item_type == ITEM_TYPE_CARD:
        item.card = _read_typed(raw.get("card"), CARD_KEYS, item, "Card")
    elif item.item_type == ITEM_TYPE_IDENTITY:
        item.identity = _read_typed(
            raw.get("identity"), IDENTITY_KEYS, item, "Contact"
        )

    if raw.get("type") not in C2_TYPE_TO_ITEM_TYPE:
        _payload_for_unknown_type(raw, item)

    item.notes = item.notes.rstrip("\r\n")
    return item


def _read_source(source: str | Path | bytes) -> str:
    """Resolve a path, bytes, or JSON text to the document's text.

    A ``str`` may be either a path or a whole JSON document, and the two are
    told apart by content rather than by asking the filesystem. Handing a
    4 KB export to ``Path.exists()`` makes the OS stat a filename far past
    NAME_MAX: Python 3.14's pathlib suppresses the resulting ENAMETOOLONG,
    but 3.10-3.13 raise it straight through the caller.
    """
    if isinstance(source, bytes):
        return _decode(source)
    if isinstance(source, Path):
        return _decode(source.read_bytes())

    text = str(source)
    if text.lstrip().startswith(("{", "[")):
        return text
    return _decode(Path(text).read_bytes())


def parse_c2_json(source: str | Path | bytes) -> list[C2Item]:
    """Parse a C2 Password JSON export into a list of :class:`C2Item`.

    ``source`` can be a path, raw bytes, or already-decoded JSON text.
    """
    data = json.loads(_read_source(source))
    if isinstance(data, dict):
        items = data.get("items")
    elif isinstance(data, list):
        items = data
    else:
        items = None

    if not isinstance(items, list):
        raise ValueError(
            'Not a C2 Password JSON export: expected an object with an "items" '
            "array, or a bare array of items."
        )
    return [_item_from(it) for it in items if isinstance(it, dict)]


def iter_c2_json(source: str | Path | bytes) -> Iterator[C2Item]:
    """Streaming-shaped variant of :func:`parse_c2_json`."""
    yield from parse_c2_json(source)
