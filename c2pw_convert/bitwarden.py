"""Writer for Bitwarden's CSV import format.

Bitwarden's import expects this column order:

    folder, favorite, type, name, notes, fields, reprompt,
    login_uri, login_username, login_password, login_totp

Multiple URIs on one item are supported by comma-separating them inside a
single ``login_uri`` cell. Bitwarden's importer re-parses the cell with
``parseSingleRowCsv`` and produces one Login URI per entry — verified
against ``bitwarden-csv-importer.ts`` in the upstream ``bitwarden/clients``
repository.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, TextIO

from .parser import C2Item

BITWARDEN_HEADERS = [
    "folder",
    "favorite",
    "type",
    "name",
    "notes",
    "fields",
    "reprompt",
    "login_uri",
    "login_username",
    "login_password",
    "login_totp",
]


def _encode_fields(custom: dict[str, str]) -> str:
    """Bitwarden custom fields use ``name: value`` pairs separated by newlines."""
    if not custom:
        return ""
    return "\n".join(f"{k}: {v}" for k, v in custom.items())


def _row_for(item: C2Item) -> dict[str, str]:
    return {
        "folder": item.tag,
        "favorite": "1" if item.favorite else "",
        "type": "login",
        "name": item.name,
        "notes": item.notes,
        "fields": _encode_fields(item.custom_fields),
        "reprompt": "0",
        "login_uri": ",".join(item.urls),
        "login_username": item.username,
        "login_password": item.password,
        "login_totp": item.totp,
    }


def write_bitwarden_csv(
    items: Iterable[C2Item],
    destination: str | Path | TextIO,
) -> None:
    rows = [_row_for(it) for it in items]
    if hasattr(destination, "write"):
        writer = csv.DictWriter(destination, fieldnames=BITWARDEN_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        return

    path = Path(destination)  # type: ignore[arg-type]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=BITWARDEN_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
