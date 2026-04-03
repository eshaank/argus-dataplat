"""CLI entry point: python -m dataplat.cli.migrate"""

from __future__ import annotations

import argparse
import logging
import sys

from dataplat.db.migrate import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ClickHouse schema migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show pending migrations without applying")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        count = run_migrations(dry_run=args.dry_run)
    except Exception as exc:
        logging.error("Migration failed: %s", exc)
        sys.exit(1)

    if count == 0:
        print("Nothing to apply — all migrations are current.")
    elif args.dry_run:
        print(f"{count} migration(s) would be applied.")
    else:
        print(f"✓ {count} migration(s) applied successfully.")


if __name__ == "__main__":
    main()
