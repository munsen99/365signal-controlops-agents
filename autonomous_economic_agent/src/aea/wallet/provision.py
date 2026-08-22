"""Operator-only Phase-B key generation/inspection. Never a service endpoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aea.signer.solana import load_protected_keypair


def generate(path: Path) -> str:
    if path.exists() or path.is_symlink():
        raise ValueError("refusing to overwrite signer key")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    from solders.keypair import Keypair
    key = Keypair()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(list(bytes(key)), stream, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return str(key.pubkey())


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-B protected signer key operator utility")
    parser.add_argument("action", choices=("generate", "public-address"))
    parser.add_argument("--key-file", required=True, type=Path)
    args = parser.parse_args()
    address = generate(args.key_file) if args.action == "generate" else str(load_protected_keypair(args.key_file).pubkey())
    print(address)  # public address only


if __name__ == "__main__":
    main()
