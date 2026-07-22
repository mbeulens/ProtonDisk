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
    sub.add_parser("gui", help="launch the graphical browser")
    mnt = sub.add_parser("mount", help="mount Proton Drive as a read-only disk")
    mnt.add_argument("mountpoint", nargs="?", default=None)
    umnt = sub.add_parser("unmount", help="unmount the Proton Drive disk")
    umnt.add_argument("mountpoint", nargs="?", default=None)
    return parser


def _cmd_mount(disk, mountpoint, *, mounter=None) -> int:
    from .mount import mounter as _mounter
    mounter = mounter or _mounter
    status = disk.auth_status()
    if not status.logged_in:
        print("error: not signed in — run 'protondisk auth-status' / 'auth login'",
              file=sys.stderr)
        return 1
    print(f"Mounted /my-files (read-write) at {mountpoint} — press Ctrl-C to unmount")
    mounter.mount(disk, mountpoint)
    return 0


def _cmd_unmount(mountpoint, *, mounter=None) -> int:
    from .mount import mounter as _mounter
    mounter = mounter or _mounter
    return 0 if mounter.unmount(mountpoint) else 1


def main(argv: list[str] | None = None, disk: ProtonDisk | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "version":
        print(protondisk.__version__)
        return 0

    if args.command == "gui":
        from protondisk.gui.app import run as run_gui
        return run_gui()

    if args.command == "unmount":
        from .mount import mounter as _mounter
        return _cmd_unmount(args.mountpoint or _mounter.default_mountpoint())
    if args.command == "mount":
        from .mount import mounter as _mounter
        mp = args.mountpoint or _mounter.default_mountpoint()
        return _cmd_mount(disk or ProtonDisk(), mp)

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
