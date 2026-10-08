#!/usr/bin/env python3
"""Administrator-only game reset with an automatic save backup.

This script is intentionally not registered as an MCP tool. Run it from the
service console only when the owner explicitly asks to start a new game.
"""

import argparse
from datetime import datetime, timedelta, timezone
import os
import shutil

import fishing


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the current fishing save and start a new game.")
    parser.add_argument(
        "--seed",
        help="Optional integer seed; hexadecimal values such as 0x9e3779b9 are accepted.",
    )
    args = parser.parse_args()

    save_file = fishing._SAVE
    backup_file = None
    if os.path.exists(save_file):
        singapore = timezone(timedelta(hours=8))
        stamp = datetime.now(singapore).strftime("%Y%m%d-%H%M%S")
        backup_file = f"{save_file}.backup-{stamp}"
        suffix = 1
        while os.path.exists(backup_file):
            backup_file = f"{save_file}.backup-{stamp}-{suffix}"
            suffix += 1
        shutil.copy2(save_file, backup_file)

    seed = int(args.seed, 0) if args.seed else None
    result = fishing.new_game(seed) if seed is not None else fishing.new_game()
    if backup_file:
        print(f"旧存档已备份：{backup_file}")
    else:
        print("没有旧存档需要备份。")
    print(result)


if __name__ == "__main__":
    main()
