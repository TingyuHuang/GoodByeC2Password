"""Command line entry point: ``python -m c2pw_convert``."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .bitwarden_json import write_bitwarden_json
from .formats import (
    LOGIN_ONLY_WRITERS,
    write_apple_csv,
    write_chrome_csv,
    write_dashlane_csv,
    write_firefox_csv,
    write_keepassxc_csv,
    write_lastpass_csv,
    write_nordpass_csv,
    write_proton_csv,
)
from .onepassword import write_onepassword_csv
from .parser import (
    ITEM_TYPE_CARD,
    ITEM_TYPE_DISPLAY,
    ITEM_TYPE_IDENTITY,
    ITEM_TYPE_LOGIN,
    ITEM_TYPE_NOTE,
    C2Item,
    parse_c2_json,
)

# The one target that emits JSON rather than CSV.
JSON_TARGET = "bitwarden"

# C2 types that Bitwarden's JSON import can represent as-is.
NATIVE_JSON_TYPES = frozenset(
    {ITEM_TYPE_LOGIN, ITEM_TYPE_CARD, ITEM_TYPE_NOTE, ITEM_TYPE_IDENTITY}
)

# Keep this dict in sorted-by-key order so --help is stable and predictable.
WRITERS = {
    "1password": write_onepassword_csv,
    "apple": write_apple_csv,
    "bitwarden": write_bitwarden_json,
    "chrome": write_chrome_csv,
    "dashlane": write_dashlane_csv,
    "firefox": write_firefox_csv,
    "keepassxc": write_keepassxc_csv,
    "lastpass": write_lastpass_csv,
    "nordpass": write_nordpass_csv,
    "proton": write_proton_csv,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="c2pw-convert",
        description=(
            "Convert a Synology C2 Password JSON export to a file another "
            "password manager can import (JSON for bitwarden, CSV otherwise)."
        ),
    )
    p.add_argument("input", type=Path, help="C2 Password JSON export file")
    p.add_argument(
        "--to",
        choices=sorted(WRITERS.keys()),
        required=True,
        help=(
            "Target password manager format. bitwarden writes Bitwarden's "
            "JSON import format and is the only lossless target: it keeps "
            "payment cards as cards, tags as real folders, and secrets as "
            "hidden fields. Every other target is CSV."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (.json for bitwarden, .csv otherwise). Defaults to stdout.",
    )
    return p


def _summarize(items: list[C2Item], target: str) -> list[str]:
    """Lines describing what was converted, and what the target can't hold."""
    counts = Counter(it.item_type for it in items)
    # Sorted by the label the reader actually sees, not the internal key.
    breakdown = ", ".join(
        f"{label}: {n}"
        for label, n in sorted(
            (ITEM_TYPE_DISPLAY.get(t, t), n) for t, n in counts.items()
        )
    )
    lines = [f"Item types: {breakdown}"] if breakdown else []

    if target == JSON_TARGET:
        # Logins, cards and notes all have a native cipher type; anything else
        # (a router today) still has to land as a Secure Note.
        degraded = sum(n for t, n in counts.items() if t not in NATIVE_JSON_TYPES)
        if degraded:
            lines.append(
                f"note: {degraded} item(s) have no native Bitwarden type and "
                "became Secure Notes with their fields attached."
            )
        return lines

    dropped = sum(n for t, n in counts.items() if t != ITEM_TYPE_LOGIN)
    if dropped and target in LOGIN_ONLY_WRITERS:
        lines.append(
            f"warning: {target} can only import logins; skipped {dropped} "
            f"non-login item(s). Convert with --to {JSON_TARGET} to keep them."
        )
    elif dropped:
        lines.append(
            f"note: {dropped} non-login item(s) were converted to notes; "
            'look for "C2 item type:" in the notes to find them.'
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    items = parse_c2_json(args.input)
    writer = WRITERS[args.to]

    if (
        args.to == JSON_TARGET
        and args.output is not None
        and args.output.suffix.lower() == ".csv"
    ):
        print(
            f"warning: --to {JSON_TARGET} writes JSON, but {args.output} has a "
            ".csv extension. Import it as 'Bitwarden (json)'.",
            file=sys.stderr,
        )

    if args.output is None:
        writer(items, sys.stdout)
    else:
        writer(items, args.output)
        print(
            f"Wrote {len(items)} item(s) to {args.output} ({args.to} format).",
            file=sys.stderr,
        )
    # Always on stderr, so it never contaminates a piped CSV on stdout.
    for line in _summarize(items, args.to):
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
