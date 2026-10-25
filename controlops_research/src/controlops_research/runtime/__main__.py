"""CLI entry. The only accepted command is `doctor`."""

from __future__ import annotations

import sys

from .doctor import doctor


def main(argv: list[str]) -> int:
    if argv != ["doctor"]:
        print("CONFIG_INVALID", file=sys.stderr)
        return 2
    return doctor()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
