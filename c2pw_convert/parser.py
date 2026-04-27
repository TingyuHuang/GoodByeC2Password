"""Parser for Synology C2 Password CSV exports.

C2 Password's CSV export only contains Login items. Headers observed in real
exports:

    Display_Name, Login_URLs, Login_URL_Match_Rules, Login_Username,
    Login_Password, Login_TOTP, Tag, Tag_Color, Favorite, Notes, Others

Quirks worth knowing:

* The file encoding is not stable. Real exports have shipped as UTF-8 (often
  with a BOM) and UTF-16. We try a short list of encodings.
* ``Login_URLs`` may contain multiple URLs separated by newlines inside a
  single quoted CSV cell.
* Empty cells sometimes arrive as the literal strings ``nan``/``none``/``null``.
* The delimiter is normally ``,`` but we use ``csv.Sniffer`` as a safety net.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp1252", "iso-8859-1")
NULLISH = {"", "nan", "none", "null"}

# Canonical header names we understand. We compare case-insensitively and
# tolerate a few aliases that have appeared in different C2 versions.
HEADER_ALIASES = {
    "display_name": "Display_Name",
    "name": "Display_Name",
    "title": "Display_Name",
    "login_urls": "Login_URLs",
    "url": "Login_URLs",
    "urls": "Login_URLs",
    "login_url_match_rules": "Login_URL_Match_Rules",
    "login_username": "Login_Username",
    "username": "Login_Username",
    "login_password": "Login_Password",
    "password": "Login_Password",
    "login_totp": "Login_TOTP",
    "totp": "Login_TOTP",
    "tag": "Tag",
    "tags": "Tag",
    "tag_color": "Tag_Color",
    "favorite": "Favorite",
    "favourite": "Favorite",
    "notes": "Notes",
    "note": "Notes",
    "others": "Others",
    "other": "Others",
}


@dataclass
class C2Item:
    """A single Login row parsed from a C2 Password export."""

    name: str = ""
    urls: list[str] = field(default_factory=list)
    url_match_rules: list[str] = field(default_factory=list)
    username: str = ""
    password: str = ""
    totp: str = ""
    tag: str = ""
    tag_color: str = ""
    favorite: bool = False
    notes: str = ""
    custom_fields: dict[str, str] = field(default_factory=dict)


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


def _sniff_dialect(sample: str) -> type[csv.Dialect] | csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    stripped = value.strip()
    if stripped.lower() in NULLISH:
        return ""
    return stripped


def _split_multi(value: str) -> list[str]:
    if not value:
        return []
    parts: list[str] = []
    for chunk in value.replace("\r\n", "\n").split("\n"):
        cleaned = chunk.strip()
        if cleaned:
            parts.append(cleaned)
    return parts


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "favorite", "★"}


def _parse_others(value: str) -> dict[str, str]:
    """Best-effort split of the free-form ``Others`` field into key/value pairs.

    C2's UI lets users add arbitrary custom fields; in the CSV they end up
    flattened. We've seen two shapes in the wild:

    * ``key: value`` pairs separated by newlines
    * ``key=value`` pairs separated by ``;``

    Anything we can't parse becomes a single ``Others`` entry so the data is
    not silently dropped.
    """

    if not value:
        return {}
    result: dict[str, str] = {}
    raw_lines = value.replace("\r\n", "\n").split("\n")
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        sep_idx = -1
        for sep in (": ", ":", "="):
            idx = line.find(sep)
            if idx != -1:
                sep_idx = idx
                sep_len = len(sep)
                break
        if sep_idx <= 0:
            result.setdefault("Others", "")
            result["Others"] = (result["Others"] + "\n" + line).strip()
            continue
        key = line[:sep_idx].strip()
        val = line[sep_idx + sep_len :].strip()
        if key:
            result[key] = val
    return result


def _build_header_index(fieldnames: Iterable[str]) -> dict[str, str]:
    """Map raw header → canonical header using HEADER_ALIASES."""
    mapping: dict[str, str] = {}
    for raw in fieldnames:
        if raw is None:
            continue
        key = raw.strip().lower().lstrip("﻿")
        canonical = HEADER_ALIASES.get(key)
        if canonical:
            mapping[raw] = canonical
    return mapping


def _row_to_item(row: dict[str, str], header_map: dict[str, str]) -> C2Item:
    canonical: dict[str, str] = {}
    for raw, value in row.items():
        target = header_map.get(raw)
        if target:
            canonical[target] = value or ""

    item = C2Item(
        name=_normalize(canonical.get("Display_Name", "")),
        urls=_split_multi(_normalize(canonical.get("Login_URLs", ""))),
        url_match_rules=_split_multi(
            _normalize(canonical.get("Login_URL_Match_Rules", ""))
        ),
        username=_normalize(canonical.get("Login_Username", "")),
        password=canonical.get("Login_Password", "") or "",
        totp=_normalize(canonical.get("Login_TOTP", "")),
        tag=_normalize(canonical.get("Tag", "")),
        tag_color=_normalize(canonical.get("Tag_Color", "")),
        favorite=_truthy(_normalize(canonical.get("Favorite", ""))),
        notes=canonical.get("Notes", "") or "",
        custom_fields=_parse_others(_normalize(canonical.get("Others", ""))),
    )
    # Passwords/notes intentionally keep internal whitespace; only trim trailing
    # newline that some exports append.
    item.password = item.password.rstrip("\r\n")
    item.notes = item.notes.rstrip("\r\n")
    return item


def parse_c2_csv(source: str | Path | bytes) -> list[C2Item]:
    """Parse a C2 Password CSV export into a list of :class:`C2Item`.

    ``source`` can be a path, raw bytes, or already-decoded text.
    """

    if isinstance(source, (str, Path)) and Path(str(source)).exists():
        data = Path(source).read_bytes()
        text = _decode(data)
    elif isinstance(source, bytes):
        text = _decode(source)
    else:
        text = str(source)

    sample = text[:4096]
    dialect = _sniff_dialect(sample)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    header_map = _build_header_index(reader.fieldnames)
    if not header_map:
        raise ValueError(
            "Could not recognize any C2 Password headers; got: "
            + ", ".join(reader.fieldnames)
        )
    return [_row_to_item(row, header_map) for row in reader]


def iter_c2_csv(source: str | Path | bytes) -> Iterator[C2Item]:
    """Streaming variant of :func:`parse_c2_csv`."""
    yield from parse_c2_csv(source)
