from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path


HEADER = ["item_id", "location_id", "trans_date", "qty", "cost_amount"]
FILE_DATE_RE = re.compile(r"stock_(\d{4})_(\d{2})_(\d{2})\.csv$")
TRANS_FILE_RE = re.compile(r"invent_trans_(\d{4})_(\d{2})\.csv$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate daily stock balances from inventory transactions."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing invent_trans/ and stock/ (default: script directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for generated stock_YYYY_MM_DD.csv files (default: <source>/stock).",
    )
    parser.add_argument(
        "--from-date",
        type=date.fromisoformat,
        default=None,
        help="First date to generate, YYYY-MM-DD (default: day after initial stock date).",
    )
    parser.add_argument(
        "--to-date",
        type=date.fromisoformat,
        default=None,
        help="Last date to generate, YYYY-MM-DD (default: last transaction date).",
    )
    return parser.parse_args()


def decimal(value: str, *, field: str, line: int, path: Path) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid {field}={value!r} in {path} at line {line}"
        ) from exc


def find_initial_stock(stock_dir: Path) -> tuple[Path, date]:
    candidates = []

    for path in stock_dir.glob("stock_*.csv"):
        match = FILE_DATE_RE.fullmatch(path.name)
        if match:
            stock_date = date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
            candidates.append((stock_date, path))

    if not candidates:
        raise FileNotFoundError(f"No stock_YYYY_MM_DD.csv found in {stock_dir}")

    stock_date, path = min(candidates)
    return path, stock_date


def load_initial_stock(path: Path) -> dict[tuple[str, str], list[Decimal]]:
    balances: dict[tuple[str, str], list[Decimal]] = {}

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")

        if reader.fieldnames != HEADER:
            raise ValueError(
                f"Unexpected header in {path}: {reader.fieldnames!r}; "
                f"expected {HEADER!r}"
            )

        for line, row in enumerate(reader, start=2):
            key = (row["item_id"], row["location_id"])

            if key in balances:
                raise ValueError(f"Duplicate key {key!r} in {path} at line {line}")

            balances[key] = [
                decimal(row["qty"], field="qty", line=line, path=path),
                decimal(row["cost_amount"], field="cost_amount", line=line, path=path),
            ]

    return balances


def load_month_transactions(
    path: Path,
) -> dict[date, dict[tuple[str, str], list[Decimal]]]:
    daily: dict[date, dict[tuple[str, str], list[Decimal]]] = defaultdict(dict)

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")

        if reader.fieldnames != HEADER:
            raise ValueError(
                f"Unexpected header in {path}: {reader.fieldnames!r}; "
                f"expected {HEADER!r}"
            )

        for line, row in enumerate(reader, start=2):
            try:
                trans_date = date.fromisoformat(row["trans_date"])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid trans_date={row['trans_date']!r} "
                    f"in {path} at line {line}"
                ) from exc

            key = (row["item_id"], row["location_id"])
            qty = decimal(row["qty"], field="qty", line=line, path=path)
            cost = decimal(row["cost_amount"], field="cost_amount", line=line, path=path)

            if key not in daily[trans_date]:
                daily[trans_date][key] = [Decimal("0"), Decimal("0")]

            daily[trans_date][key][0] += qty
            daily[trans_date][key][1] += cost

    return daily


def transaction_files(trans_dir: Path, initial_date: date) -> list[Path]:
    files = []

    for path in trans_dir.glob("invent_trans_*.csv"):
        match = TRANS_FILE_RE.fullmatch(path.name)
        if not match:
            continue

        year = int(match.group(1))
        month = int(match.group(2))
        month_start = date(year, month, 1)

        if month_start > initial_date:
            files.append(path)

    return sorted(files)


def write_stock(path: Path, stock_date: date, balances: dict[tuple[str, str], list[Decimal]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(
            file,
            delimiter=";",
            quotechar='"',
            quoting=csv.QUOTE_ALL,
            lineterminator="\n",
        )
        writer.writerow(HEADER)

        for item_id, location_id in sorted(balances):
            qty, cost = balances[(item_id, location_id)]
            writer.writerow(
                [
                    item_id,
                    location_id,
                    stock_date.isoformat(),
                    format(qty, "f"),
                    format(cost, "f"),
                ]
            )


def calculate(
    source: Path,
    output: Path,
    from_date: date | None = None,
    to_date: date | None = None,
) -> None:
    trans_dir = source / "invent_trans"
    stock_dir = source / "stock"

    initial_path, initial_date = find_initial_stock(stock_dir)
    balances = load_initial_stock(initial_path)

    files = transaction_files(trans_dir, initial_date)
    if not files:
        raise FileNotFoundError(f"No transaction files found in {trans_dir}")


    last_transaction_date = None
    for path in files:
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file, delimiter=";")
            for line, row in enumerate(reader, start=2):
                try:
                    current_date = date.fromisoformat(row["trans_date"])
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid trans_date={row['trans_date']!r} "
                        f"in {path} at line {line}"
                    ) from exc

                if last_transaction_date is None or current_date > last_transaction_date:
                    last_transaction_date = current_date

    start = from_date or (initial_date + timedelta(days=1))
    end = to_date or last_transaction_date

    if end is None:
        raise ValueError("No transactions found")
    if start > end:
        raise ValueError(f"from-date {start} is after to-date {end}")
    if start <= initial_date:
        raise ValueError(
            f"from-date must be after initial stock date {initial_date}"
        )

    output.mkdir(parents=True, exist_ok=True)

    current = initial_date + timedelta(days=1)
    file_index = 0

    while current <= end:
        current_month = (current.year, current.month)
        month_file = None

        while file_index < len(files):
            match = TRANS_FILE_RE.fullmatch(files[file_index].name)
            file_month = (int(match.group(1)), int(match.group(2)))

            if file_month < current_month:
                file_index += 1
                continue

            if file_month == current_month:
                month_file = files[file_index]
            break

        daily: dict[date, dict[tuple[str, str], list[Decimal]]] = {}
        if month_file is not None:
            daily = load_month_transactions(month_file)
            file_index += 1

        next_month = (
            date(current.year + 1, 1, 1)
            if current.month == 12
            else date(current.year, current.month + 1, 1)
        )
        month_end = min(end, next_month - timedelta(days=1))

        while current <= month_end:
            for key, movement in daily.get(current, {}).items():
                if key not in balances:
                    balances[key] = [Decimal("0"), Decimal("0")]

                balances[key][0] += movement[0]
                balances[key][1] += movement[1]

            if current >= start:
                output_path = output / f"stock_{current:%Y_%m_%d}.csv"
                write_stock(output_path, current, balances)
            current += timedelta(days=1)


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = (args.output or source / "stock").resolve()
    calculate(source, output, args.from_date, args.to_date)
    print(f"Daily stock files written to: {output}")


if __name__ == "__main__":
    main()
