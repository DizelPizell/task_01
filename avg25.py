from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


AVG_QUANT = Decimal("0.001")
THRESHOLD = Decimal("0.25")


def read_daily_stock(path: Path) -> dict[tuple[str, str], Decimal]:
    """Read one daily stock file and return qty by (item_id, location_id)."""
    result: dict[tuple[str, str], Decimal] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        required = {"item_id", "location_id", "trans_date", "qty", "cost_amount"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError(f"{path}: missing required columns")

        for row in reader:
            key = (row["item_id"], row["location_id"])
            result[key] = Decimal(row["qty"])

    return result


def calculate(stock_dir: Path, output: Path) -> None:
    start = date(2025, 7, 1)
    end = date(2025, 7, 31)

    sums: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    daily: dict[str, dict[tuple[str, str], Decimal]] = {}

    current = start
    while current <= end:
        ds = current.isoformat()
        path = stock_dir / f"stock_{current:%Y_%m_%d}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Daily stock file not found: {path}")

        stock = read_daily_stock(path)
        positive = {key: qty for key, qty in stock.items() if qty != 0}
        daily[ds] = positive

        for key, qty in positive.items():
            sums[key] += qty
            counts[key] += 1

        current += timedelta(days=1)

    result = []
    for key, total in sums.items():
        avg = (total / counts[key]).quantize(AVG_QUANT, rounding=ROUND_HALF_UP)
        threshold = avg * THRESHOLD

        for ds in sorted(daily):
            qty = daily[ds].get(key)
            if qty is not None and qty < threshold:
                result.append((key[0], key[1], ds, qty, avg))
                break

    result.sort(key=lambda row: (row[1], row[0], row[2]))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["item_id", "location_id", "trans_date", "qty", "qty_avg"])
        for item_id, location_id, trans_date, qty, avg in result:
            writer.writerow([
                item_id,
                location_id,
                trans_date,
                format(qty, "f"),
                format(avg, "f"),
            ])

    print(f"Rows written: {len(result)}")
    print(f"Output: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find first July 2025 stock incidents below 25% of average."
    )
    parser.add_argument(
        "--stock-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "stock",
        help="Directory containing stock_YYYY_MM_DD.csv files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "stock_2025_07_avg25.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()
    calculate(args.stock_dir, args.output)


if __name__ == "__main__":
    main()
