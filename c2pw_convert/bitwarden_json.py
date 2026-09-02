"""Writer for Bitwarden's JSON import format.

This is the only target that can hold a C2 export without losing anything.
Bitwarden's *CSV* importer understands exactly two ``type`` values — ``note``
and "everything else, which is a Login" — so a C2 payment card has to be
flattened into a Secure Note there. The JSON importer takes the real cipher
types, so a card imports as a Card, a folder is a real folder, an item can
have several URIs, and secret custom fields can be marked hidden.

Structure (per Bitwarden's documented import format)::

    {
      "folders": [{"id": <uuid>, "name": "..."}],
      "items": [{
        "id": <uuid>, "organizationId": null, "folderId": <uuid|null>,
        "type": 1, "reprompt": 0, "name": "...", "notes": "...",
        "favorite": false,
        "fields": [{"name": "...", "value": "...", "type": 0}],
        "login": {"uris": [{"match": null, "uri": "..."}],
                  "username": "...", "password": "...", "totp": "..."},
        "collectionIds": null
      }]
    }

``type``: 1 Login, 2 Secure Note, 3 Card, 4 Identity.
``fields[].type``: 0 text, 1 hidden.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Iterable, TextIO

from ._util import merged_notes
from .parser import (
    ITEM_TYPE_CARD,
    ITEM_TYPE_IDENTITY,
    ITEM_TYPE_LOGIN,
    ITEM_TYPE_NOTE,
    C2Item,
)

CIPHER_TYPE_LOGIN = 1
CIPHER_TYPE_SECURE_NOTE = 2
CIPHER_TYPE_CARD = 3
CIPHER_TYPE_IDENTITY = 4

CIPHER_TYPE_FOR = {
    ITEM_TYPE_LOGIN: CIPHER_TYPE_LOGIN,
    ITEM_TYPE_NOTE: CIPHER_TYPE_SECURE_NOTE,
    ITEM_TYPE_CARD: CIPHER_TYPE_CARD,
    ITEM_TYPE_IDENTITY: CIPHER_TYPE_IDENTITY,
}

FIELD_TYPE_TEXT = 0
FIELD_TYPE_HIDDEN = 1

SECURE_NOTE_TYPE_GENERIC = 0

# Fixed namespace so the same export always produces the same ids. Re-running
# the converter then yields a byte-identical file, which makes it diffable and
# means a re-import doesn't look like a different vault.
_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _uuid_for(*parts: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, "\x1f".join(parts)))


def _fields_for(item: C2Item, skip: set[str] = frozenset()) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "value": value,
            "type": (
                FIELD_TYPE_HIDDEN
                if name in item.sensitive_fields
                else FIELD_TYPE_TEXT
            ),
        }
        for name, value in item.custom_fields.items()
        if name not in skip
    ]


def _normalized_card(item: C2Item) -> dict[str, str]:
    """Copy the card through, nudging month/year into what Bitwarden expects.

    C2 writes a zero-padded month and a two-digit year (``01`` / ``23``);
    Bitwarden's card form matches on an unpadded month and a four-digit year.
    """
    card = dict(item.card)
    month = card.get("expMonth", "").lstrip("0")
    if month:
        card["expMonth"] = month
    year = card.get("expYear", "")
    if len(year) == 2 and year.isdigit():
        card["expYear"] = "20" + year
    return card


def _item_payload(item: C2Item, index: int, folder_ids: dict[str, str]) -> dict[str, Any]:
    cipher_type = CIPHER_TYPE_FOR.get(item.item_type, CIPHER_TYPE_SECURE_NOTE)
    payload: dict[str, Any] = {
        "id": _uuid_for("item", str(index), item.name),
        "organizationId": None,
        "folderId": folder_ids.get(item.tag),
        "type": cipher_type,
        "reprompt": 0,
        "name": item.name or "--",
        "favorite": item.favorite,
        # Every C2 attribute that isn't part of a typed payload is its own
        # Bitwarden custom field — never several values packed into one.
        "fields": _fields_for(item),
        "collectionIds": None,
    }

    if cipher_type == CIPHER_TYPE_LOGIN:
        payload["notes"] = item.notes or None
        payload["login"] = {
            "uris": [{"match": None, "uri": url} for url in item.urls],
            "username": item.username,
            "password": item.password,
            "totp": item.totp,
        }
        return payload

    if cipher_type == CIPHER_TYPE_CARD:
        payload["notes"] = item.notes or None
        payload["card"] = _normalized_card(item)
        return payload

    if cipher_type == CIPHER_TYPE_IDENTITY:
        payload["notes"] = item.notes or None
        payload["identity"] = dict(item.identity)
        return payload

    # Secure notes, and any C2 type Bitwarden has no cipher for. The payload
    # already arrived itemized in `fields`, so there is nothing to flatten
    # here; we only stamp the original type when it wasn't a note to begin
    # with, so the item can be found and re-typed by hand later.
    payload["notes"] = (
        merged_notes(
            item,
            include_custom=False,
            include_extra_urls=False,
            include_structured=False,
            include_type=item.item_type != ITEM_TYPE_NOTE,
        )
        or None
    )
    payload["secureNote"] = {"type": SECURE_NOTE_TYPE_GENERIC}
    return payload


def build_bitwarden_export(items: Iterable[C2Item]) -> dict[str, Any]:
    """Build the importable dict. Split out so tests can inspect it directly."""
    items_list = list(items)

    # C2 tags become real Bitwarden folders rather than a name in a column.
    folder_ids: dict[str, str] = {}
    folders: list[dict[str, str]] = []
    for it in items_list:
        if it.tag and it.tag not in folder_ids:
            folder_ids[it.tag] = _uuid_for("folder", it.tag)
            folders.append({"id": folder_ids[it.tag], "name": it.tag})

    return {
        "encrypted": False,
        "folders": folders,
        "items": [_item_payload(it, i, folder_ids) for i, it in enumerate(items_list)],
    }


def write_bitwarden_json(
    items: Iterable[C2Item],
    destination: str | Path | TextIO,
) -> None:
    payload = build_bitwarden_export(items)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    if hasattr(destination, "write"):
        destination.write(text)  # type: ignore[union-attr]
        return
    Path(destination).write_text(text, encoding="utf-8")  # type: ignore[arg-type]
