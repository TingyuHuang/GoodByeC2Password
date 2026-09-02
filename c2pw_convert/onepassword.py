"""Writer for 1Password's CSV import format.

The 1Password desktop importer accepts a CSV with these columns for Login
items:

    Title, Url, Username, Password, OTPAuth, Favorite, Tags, Notes

Custom fields are appended as additional columns; 1Password treats any column
beyond the known ones as a string field on the resulting Login item, named
after the column header.

This CSV has no type column — every row becomes a Login. C2's cards, secure
notes and routers therefore arrive as Logins whose custom fields hold the
payload, with the original type stamped into Notes so they can be found and
re-typed by hand afterwards.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, TextIO

from ._util import merged_notes, otpauth_uri
from .parser import C2Item

ONEPASSWORD_BASE_HEADERS = [
    "Title",
    "Url",
    "Username",
    "Password",
    "OTPAuth",
    "Favorite",
    "Tags",
    "Notes",
]


# Backwards-compatible alias for the helper that used to live here.
_otpauth_uri = otpauth_uri


def _row_for(item: C2Item, custom_headers: list[str]) -> list[str]:
    primary_url = item.urls[0] if item.urls else ""
    issuer = item.name or (item.urls[0] if item.urls else "")
    base = [
        item.name,
        primary_url,
        item.username,
        item.password,
        otpauth_uri(item.totp, item.username, issuer),
        "Y" if item.favorite else "",
        item.tag,
        merged_notes(item, include_custom=False, include_extra_urls=False),
    ]
    extras = [item.custom_fields.get(h, "") for h in custom_headers]
    # Extra URLs beyond the first go into a synthetic column so they aren't lost.
    if len(item.urls) > 1 and "Additional URLs" in custom_headers:
        idx = custom_headers.index("Additional URLs")
        extras[idx] = "\n".join(item.urls[1:])
    return base + extras


def write_onepassword_csv(
    items: Iterable[C2Item],
    destination: str | Path | TextIO,
) -> None:
    items_list = list(items)

    custom_headers: list[str] = []
    seen: set[str] = set()
    for it in items_list:
        for key in it.custom_fields:
            if key not in seen and key not in ONEPASSWORD_BASE_HEADERS:
                seen.add(key)
                custom_headers.append(key)
        if len(it.urls) > 1 and "Additional URLs" not in seen:
            seen.add("Additional URLs")
            custom_headers.append("Additional URLs")

    headers = ONEPASSWORD_BASE_HEADERS + custom_headers
    rows = [_row_for(it, custom_headers) for it in items_list]

    if hasattr(destination, "write"):
        writer = csv.writer(destination)
        writer.writerow(headers)
        writer.writerows(rows)
        return

    path = Path(destination)  # type: ignore[arg-type]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)
