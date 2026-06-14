#!/usr/bin/env python3
"""
Convert between .NET ticks (TransactionTS) and human-readable timestamps.

.NET ticks = 100-nanosecond intervals since 0001-01-01 00:00:00.

Usage:
    # Timestamp → Ticks
    ./tick_convert.py "2026-03-12 08:39:34"
    ./tick_convert.py "2026-03-12 08:39:34.123"

    # Ticks → Timestamp
    ./tick_convert.py 639089015740000000

    # Detect automatically
    ./tick_convert.py 639089015740000000          → ticks → datetime
    ./tick_convert.py "2026-03-12 08:39:34"        → datetime → ticks
"""

from datetime import datetime, timedelta
import sys

EPOCH_START = datetime(1, 1, 1)


def dt_to_ticks(dt: datetime) -> int:
    """Convert Python datetime to .NET ticks."""
    return int((dt - EPOCH_START).total_seconds() * 10_000_000)


def ticks_to_dt(ticks: int) -> datetime:
    """Convert .NET ticks to Python datetime."""
    return EPOCH_START + timedelta(seconds=ticks / 10_000_000)


def parse_timestamp(s: str) -> datetime:
    """Parse a timestamp string, with or without fractional seconds."""
    s = s.strip().strip('"').strip("'")
    # Try with fractional seconds first
    for fmt in ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Could not parse timestamp: {s}")


def print_help():
    """Print help text."""
    print(__doc__.strip())
    print()
    print("Options:")
    print("  --help, -h    Show this help message and exit")
    print()
    print("Auto-detection:")
    print("  All-numeric input (no separators) → treated as .NET ticks")
    print("  Input with separators (-, /, :)  → treated as timestamp")
    print()
    print("The conversion formula matches the one used by 'journal last-txn':")
    print("  ticks = (datetime - 0001-01-01).total_seconds() * 10_000_000")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print_help()
        return 0 if len(sys.argv) >= 2 else 1

    raw = sys.argv[1].strip()

    # Heuristic: if it's all digits (possibly with leading '-'), it's ticks
    if raw.lstrip("-").isdigit():
        ticks = int(raw)
        dt = ticks_to_dt(ticks)
        print(f"TransactionTS: {ticks}")
        print(f"    Timestamp: {dt}")
        print(f"        (UTC) : {dt.strftime('%Y-%m-%d %H:%M:%S.%f')}")
    else:
        dt = parse_timestamp(raw)
        ticks = dt_to_ticks(dt)
        print(f"    Timestamp: {dt}")
        print(f"TransactionTS: {ticks}")
        print(f"        (UTC) : {dt.strftime('%Y-%m-%d %H:%M:%S.%f')} -> {ticks}")

    # Also show the formatted output as used by 'journal last-txn'
    print()
    print("---")
    print(f"journal last-txn would display:")
    print(f"  Datetime:       {dt}")
    print(f"  TransactionTS:  {ticks}")


if __name__ == "__main__":
    sys.exit(main())
