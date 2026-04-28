"""Internal helpers shared by every format writer."""

from __future__ import annotations

import csv
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO
from urllib.parse import quote

from .parser import C2Item


def otpauth_uri(secret: str, account: str, issuer: str) -> str:
    """Wrap a bare TOTP secret into an ``otpauth://totp/...`` URI.

    Already-formed otpauth URIs pass through unchanged. Empty input returns
    empty.
    """
    if not secret:
        return ""
    if secret.lower().startswith("otpauth://"):
        return secret
    if issuer and account:
        label = f"{issuer}:{account}"
    else:
        label = issuer or account or "C2"
    params = f"secret={secret}"
    if issuer:
        params += f"&issuer={quote(issuer)}"
    return f"otpauth://totp/{quote(label)}?{params}"


def primary_url(item: C2Item) -> str:
    return item.urls[0] if item.urls else ""


def extra_urls_block(item: C2Item) -> str:
    """Format URLs after the first as a labeled multi-line block, or empty."""
    if len(item.urls) <= 1:
        return ""
    rest = "\n".join(item.urls[1:])
    return f"Additional URLs:\n{rest}"


def merged_notes(item: C2Item, *, include_custom: bool = True, include_extra_urls: bool = True) -> str:
    """Combine notes, custom fields, and overflow URLs into a single text blob.

    Most importers only have one free-text "notes" column, so anything that
    doesn't have a dedicated home gets glued in here so we never silently
    drop data.
    """
    parts: list[str] = []
    if item.notes:
        parts.append(item.notes)

    if include_custom and item.custom_fields:
        if parts:
            parts.append("")
        parts.append("--- Custom fields ---")
        for k, v in item.custom_fields.items():
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
