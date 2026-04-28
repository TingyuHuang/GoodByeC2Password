"""Command line entry point: ``python -m c2pw_convert``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bitwarden import write_bitwarden_csv
from .formats import (
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
from .parser import parse_c2_csv

# Keep this dict in sorted-by-key order so --help is stable and predictable.
WRITERS = {
    "1password": write_onepassword_csv,
    "apple": write_apple_csv,
    "bitwarden": write_bitwarden_csv,
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
            "Convert a Synology C2 Password CSV export to a CSV that another "
            "password manager can import."
        ),
    )
    p.add_argument("input", type=Path, help="C2 Password CSV export file")
    p.add_argument(
        "--to",
        choices=sorted(WRITERS.keys()),
        required=True,
        help=(
            "Target password manager format. "
            "Supported: 1password, apple, bitwarden, chrome, dashlane, "
            "firefox, keepassxc, lastpass, nordpass, proton."
        ),
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV path. Defaults to stdout.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    items = parse_c2_csv(args.input)
    writer = WRITERS[args.to]

    if args.output is None:
        writer(items, sys.stdout)
    else:
        writer(items, args.output)
        print(
            f"Wrote {len(items)} item(s) to {args.output} ({args.to} format).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
