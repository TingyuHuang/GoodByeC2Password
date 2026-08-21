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
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

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


def _format_address(addr: dict[str, Any]) -> str:
    parts: list[str] = []
    line = addr.get("Address", "")
    if line:
        parts.append(str(line))
    locality_bits = [
        addr.get("City_Town", ""),
        addr.get("County_District", ""),
        addr.get("Province_State", ""),
        addr.get("Postal", ""),
    ]
    locality = ", ".join(str(b) for b in locality_bits if b)
    if locality:
        parts.append(locality)
    location = addr.get("Location", "")
    if location:
        parts.append(str(location))
    return "\n".join(parts)


def _flatten_others_json(data: Any) -> dict[str, str]:
    """Flatten C2's ``Others`` JSON object into ``{title: value}`` pairs.

    Real C2 exports use this shape::

        {"Custom": [
            {"Type": "Text",     "Text_Title": "...",     "Text": "..."},
            {"Type": "Password", "Password_Title": "...", "Password": "..."},
            {"Type": "TOTP",     "TOTP_Title": "...",     "TOTP_Key": "..."},
            {"Type": "Address",  "Address_Title": "...",  "Address": {...}},
        ]}

    Each typed entry is reduced to its title and a string value. Address
    sub-objects are joined into a multi-line string so they survive the
    round-trip into plain CSV cells.

    When the JSON does not match the ``{"Custom": [...]}`` shape (e.g. a bare
    array, or a dict without a ``Custom`` key), we preserve the raw JSON
    under a single ``Others`` key rather than silently dropping it. That way
    a future C2 format tweak still surfaces the data downstream instead of
    disappearing.
    """
    if isinstance(data, dict) and isinstance(data.get("Custom"), list):
        return _flatten_custom_list(data["Custom"])

    # Unrecognized shape: keep the raw JSON so nothing gets silently dropped.
    return {"Others": json.dumps(data, ensure_ascii=False)}


def _flatten_custom_list(custom: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for idx, entry in enumerate(custom):
        if not isinstance(entry, dict):
            continue
        type_ = entry.get("Type", "")
        title_key = f"{type_}_Title"
        title = str(entry.get(title_key, "")).strip()
        if type_ == "Text":
            value = entry.get("Text", "")
        elif type_ == "Password":
            value = entry.get("Password", "")
        elif type_ == "TOTP":
            value = entry.get("TOTP_Key", "")
        elif type_ == "Address":
            raw = entry.get("Address", "")
            value = _format_address(raw) if isinstance(raw, dict) else raw
        else:
            # Unknown type: keep whatever non-meta fields are present.
            extras = {k: v for k, v in entry.items() if k not in {"Type", title_key}}
            value = json.dumps(extras, ensure_ascii=False) if extras else ""

        key = title or f"{type_ or 'Custom'}_{idx + 1}"
        # Avoid clobbering duplicate titles by appending an index.
        if key in result:
            key = f"{key} ({idx + 1})"
        result[key] = "" if value is None else str(value)
    return result


def _parse_others(value: str) -> dict[str, str]:
    """Parse C2's ``Others`` field.

    Real exports embed JSON. Older notes / hand-written CSVs sometimes used
    ``key: value`` lines, so we keep a fallback for that shape too. Anything
    we genuinely can't understand is preserved under a single ``Others`` key
    so data is never silently dropped.
    """
    if not value:
        return {}

    stripped = value.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return _flatten_others_json(json.loads(value))
        except json.JSONDecodeError:
            pass  # fall through to line-based parsing

    result: dict[str, str] = {}
    raw_lines = value.replace("\r\n", "\n").split("\n")
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        sep_idx = -1
        sep_len = 0
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
