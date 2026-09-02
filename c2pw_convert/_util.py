"""Internal helpers shared by every format writer."""

from __future__ import annotations

import csv
from contextlib import contextmanager
from pathlib import Path
from typing import Container, Iterator, TextIO
from urllib.parse import quote

from .parser import ITEM_TYPE_DISPLAY, ITEM_TYPE_LOGIN, C2Item, humanize


def otpauth_uri(secret: str, account: str, issuer: str) -> str:
    """Wrap a bare TOTP secret into an ``otpauth://totp/...`` URI.

    Already-formed otpauth URIs pass through unchanged. Empty input returns
    empty.

    The ``secret`` value is URL-encoded because Base32 secrets frequently end
    with ``=`` padding, which — if left raw in a query string — reads as
    another ``key=`` boundary to strict URI parsers.
    """
    if not secret:
        return ""
    if secret.lower().startswith("otpauth://"):
        return secret
    if issuer and account:
        label = f"{issuer}:{account}"
    else:
        label = issuer or account or "C2"
    params = f"secret={quote(secret, safe='')}"
    if issuer:
        params += f"&issuer={quote(issuer)}"
    return f"otpauth://totp/{quote(label)}?{params}"


def type_label(item: C2Item) -> str:
    """Human label for a non-login item; empty string for logins.

    Most target formats collapse cards/notes/routers into one generic type,
    so we stamp the original C2 type into the notes blob — otherwise a card
    and a login are indistinguishable after the migration.
    """
    if item.item_type == ITEM_TYPE_LOGIN:
        return ""
    return ITEM_TYPE_DISPLAY.get(
        item.item_type, item.item_type.replace("_", " ").capitalize()
    )


def structured_fields(item: C2Item) -> dict[str, str]:
    """The card or identity payload as ``label -> value`` pairs.

    CSV targets have no typed card or identity columns, so these values have
    to be written out one line per value. They are never joined into a single
    blob: a reader (or a later re-import) can still tell the parts apart.
    """
    out: dict[str, str] = {}
    for key, value in {**item.card, **item.identity}.items():
        if value:
            out[humanize(key)] = value
    return out


def primary_url(item: C2Item) -> str:
    return item.urls[0] if item.urls else ""


def extra_urls_block(item: C2Item) -> str:
    """Format URLs after the first as a labeled multi-line block, or empty."""
    if len(item.urls) <= 1:
        return ""
    rest = "\n".join(item.urls[1:])
    return f"Additional URLs:\n{rest}"


def merged_notes(
    item: C2Item,
    *,
    include_custom: bool = True,
    include_extra_urls: bool = True,
    include_type: bool = True,
    include_structured: bool = True,
    exclude_fields: Container[str] = (),
) -> str:
    """Combine notes, custom fields, and overflow URLs into a single text blob.

    Most importers only have one free-text "notes" column, so anything that
    doesn't have a dedicated home gets glued in here so we never silently
    drop data.

    ``exclude_fields`` skips custom fields the caller has already written to a
    dedicated column, so nothing is duplicated (and no card number is written
    twice).
    """
    parts: list[str] = []

    label = type_label(item) if include_type else ""
    if label:
        parts.append(f"C2 item type: {label}")

    if item.notes:
        if parts:
            parts.append("")
        parts.append(item.notes)

    if include_structured:
        structured = [
            (k, v) for k, v in structured_fields(item).items()
            if k not in exclude_fields
        ]
        if structured:
            if parts:
                parts.append("")
            parts.append(f"--- {type_label(item) or 'Details'} ---")
            for k, v in structured:
                parts.append(f"{k}: {v}")

    if include_custom:
        shown = [
            (k, v) for k, v in item.custom_fields.items() if k not in exclude_fields
        ]
        if shown:
            if parts:
                parts.append("")
            parts.append("--- Custom fields ---")
            for k, v in shown:
                parts.append(f"{k}: {v}")

    if include_extra_urls:
        block = extra_urls_block(item)
        if block:
            if parts:
                parts.append("")
            parts.append(block)

    return "\n".join(parts)


@contextmanager
def open_csv_writer(
    destination: str | Path | TextIO,
    headers: list[str],
) -> Iterator[csv.writer]:
    """Yield a ``csv.writer`` whether ``destination`` is a stream or a path."""
    if hasattr(destination, "write"):
        writer = csv.writer(destination)
        writer.writerow(headers)
        yield writer
        return
    path = Path(destination)  # type: ignore[arg-type]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        yield writer
