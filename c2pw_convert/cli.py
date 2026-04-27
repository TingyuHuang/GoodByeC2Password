"""Command line entry point: ``python -m c2pw_convert``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bitwarden import write_bitwarden_csv
from .onepassword import write_onepassword_csv
from .parser import parse_c2_csv

WRITERS = {
    "bitwarden": write_bitwarden_csv,
    "1password": write_onepassword_csv,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="c2pw-convert",
        description="Convert a Synology C2 Password CSV export to Bitwarden or 1Password CSV.",
    )
    p.add_argument("input", type=Path, help="C2 Password CSV export file")
    p.add_argument(
        "--to",
        choices=sorted(WRITERS.keys()),
        required=True,
        help="Target password manager format",
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
