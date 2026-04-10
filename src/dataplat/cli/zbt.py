"""CLI entry point: python -m dataplat.cli.zbt

Computes Zweig Breadth Thrust indicator from ohlcv_daily → zbt_breadth table.

Usage:
    just zbt                  # compute and write
    just zbt --dry-run        # compute only, don't write
    just zbt --status         # show latest ZBT status from table
"""

from __future__ import annotations

import argparse
import logging

from dataplat.db.client import get_client


def _print_status() -> None:
    """Read zbt_breadth table and print current status."""
    ch = get_client()
    result = ch.query(
        """
        SELECT day, advancing, declining, total, breadth_ratio, ema_10,
               oversold, thrust, signal_active, days_in_window, signal_fired
        FROM zbt_breadth FINAL
        ORDER BY day DESC
        LIMIT 15
        """
    )
    if not result.result_rows:
        print("No data in zbt_breadth. Run: just zbt")
        return

    latest = result.result_rows[0]
    rows = list(reversed(result.result_rows))

    print("\n" + "=" * 60)
    print("  ZWEIG BREADTH THRUST — STATUS")
    print("=" * 60)
    print(f"\n  Date:             {latest[0]}")
    print(f"  10-day EMA:       {latest[5]:.4f}")
    print(f"  Breadth ratio:    {latest[4]:.4f}  ({latest[1]} adv / {latest[2]} dec)")

    if latest[10]:  # signal_fired
        print("\n  🚀 ZBT SIGNAL FIRED!")
    elif latest[8]:  # signal_active
        remaining = 10 - (latest[9] or 0)
        needed = 0.615 - latest[5]
        print(f"\n  ⏱  SETUP ACTIVE — need +{needed:.4f} to 0.615, {remaining} days left")
    elif latest[6]:  # oversold
        print("\n  ⬇  OVERSOLD — watching for thrust")
    else:
        print("\n  —  No active setup")

    print(f"\n  {'Date':<12} {'Adv':>5} {'Dec':>5} {'Ratio':>7} {'EMA-10':>7}  Status")
    print("  " + "-" * 55)
    for r in rows:
        day, adv, dec, _, ratio, ema, oversold, thrust, active, diw, fired = r
        flag = ""
        if fired:
            flag = "🚀 SIGNAL"
        elif oversold:
            flag = "⬇ OVERSOLD"
        elif active:
            flag = f"⏱ {10 - (diw or 0)}d left"
        elif thrust:
            flag = "⬆ THRUST"
        print(f"  {day}  {adv:>5} {dec:>5}  {ratio:.4f}  {ema:.4f}  {flag}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zweig Breadth Thrust compute pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write to ClickHouse")
    parser.add_argument("--status", action="store_true", help="Show latest ZBT status from table")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.status:
        _print_status()
        return

    from dataplat.analysis.zbt import run_zbt

    run_zbt(dry_run=args.dry_run)

    if not args.dry_run:
        _print_status()


if __name__ == "__main__":
    main()
