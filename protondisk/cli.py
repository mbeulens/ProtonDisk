"""Thin command-line entrypoint exercising the ProtonDisk core."""
from __future__ import annotations

import argparse
import sys

import protondisk
from .core.client import ProtonDisk
from .core.errors import ProtonDiskError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="protondisk")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="print the ProtonDisk version")
    sub.add_parser("auth-status", help="show login status")
    ls = sub.add_parser("ls", help="list a Drive folder")
    ls.add_argument("path")
    return parser


def main(argv: list[str] | None = None, disk: ProtonDisk | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "version":
        print(protondisk.__version__)
        return 0

    try:
        disk = disk or ProtonDisk()
        if args.command == "auth-status":
            status = disk.auth_status()
            print(f"logged in as {status.account}" if status.logged_in else "not logged in")
        elif args.command == "ls":
            for entry in disk.list(args.path):
                print(f"{'/' if entry.is_dir else ' '} {entry.name}")
    except ProtonDiskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
