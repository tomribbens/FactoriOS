"""Tiny CLI for poking at the launcher without going through the greeter."""

from __future__ import annotations

import argparse
import getpass
import sys

from . import paths, versions
from .auth import AuthError, Session
from .download import latest_releases


def main() -> int:
    p = argparse.ArgumentParser(prog="factorios-launcher")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("releases", help="Print latest-releases JSON (no auth needed)")

    login = sub.add_parser("login", help="Login and cache the session")
    login.add_argument("username")

    install = sub.add_parser("install", help="Download and install a version")
    install.add_argument("username")
    install.add_argument("version", help="e.g. 1.1.110 or latest")
    install.add_argument(
        "build",
        nargs="?",
        choices=list(paths.ALL_BUILDS),
        default=paths.DEFAULT_BUILD,
        help=f"vanilla or space-age (default: {paths.DEFAULT_BUILD})",
    )

    sub.add_parser("list", help="List installed versions")
    sub.add_parser("demo", help="Download the Factorio demo (no auth needed)")

    args = p.parse_args()

    if args.cmd == "releases":
        import json as _json
        print(_json.dumps(latest_releases(Session()), indent=2))
        return 0

    if args.cmd == "list":
        for v, b in versions.list_installed():
            print(f"{v}\t{b}")
        return 0

    if args.cmd == "login":
        s = Session()
        try:
            s.login(args.username, getpass.getpass("factorio.com password: "))
        except AuthError as e:
            print(f"login failed: {e}", file=sys.stderr)
            return 1
        s.save(paths.user_session(args.username))
        print(f"session saved to {paths.user_session(args.username)}")
        return 0

    if args.cmd == "demo":
        def progress(done, total):
            pct = (done / total * 100) if total else 0
            print(f"\r{done/1e6:.1f} / {total/1e6:.1f} MB ({pct:.0f}%)", end="", flush=True)
        versions.install_demo(progress=progress)
        print()
        return 0

    if args.cmd == "install":
        sess_path = paths.user_session(args.username)
        if not sess_path.exists():
            print(f"no cached session for {args.username}; run `login` first", file=sys.stderr)
            return 1
        s = Session.load(sess_path)
        def progress(done, total):
            pct = (done / total * 100) if total else 0
            print(f"\r{done/1e6:.1f} / {total/1e6:.1f} MB ({pct:.0f}%)", end="", flush=True)
        versions.install(s, args.version, build=args.build, progress=progress)
        print()
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
