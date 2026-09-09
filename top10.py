from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

DATE_FORMAT = '%Y-%m-%d'


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def iter_csv(path: Path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        required = {'item_id', 'location_id', 'trans_date', 'qty', 'cost_amount'}
        if set(reader.fieldnames or ()) != required:
            raise ValueError(f'{path}: expected columns {sorted(required)}, got {reader.fieldnames}')
        yield from reader


def load_initial_stock(path: Path):
    stock = {}
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            key = (row['item_id'], row['location_id'])
            stock[key] = [Decimal(row['qty']), Decimal(row['cost_amount'])]
    return stock


def load_transactions(trans_dir: Path):
    by_day = defaultdict(lambda: defaultdict(lambda: [Decimal('0'), Decimal('0')]))
    for path in sorted(trans_dir.glob('invent_trans_*.csv')):
        for row in iter_csv(path):
            d = parse_date(row['trans_date'])
            key = (row['item_id'], row['location_id'])
            agg = by_day[d][key]
            agg[0] += Decimal(row['qty'])
            agg[1] += Decimal(row['cost_amount'])
    return by_day


def calculate(source: Path):
    stock_dir = source / 'stock'
    trans_dir = source / 'invent_trans'
    initial_files = sorted(stock_dir.glob('stock_*.csv'))
    if not initial_files:
        raise FileNotFoundError(f'No stock files found in {stock_dir}')
    initial_path = min(initial_files)
    stock = load_initial_stock(initial_path)
    movements = load_transactions(trans_dir)

    start = date(2025, 5, 1)
    end = date(2025, 7, 31)

    always_present = {key: True for key in stock}

    appearance_candidates = set()
    continuous_after_appearance = {}

    previous_qty = {key: value[0] for key, value in stock.items()}
    b_started = {}
    b_failed = set()

    d = start
    while d <= end:
        day_movements = movements.get(d, {})
        keys = set(stock) | set(day_movements)
        for key in keys:
            if key not in stock:
                stock[key] = [Decimal('0'), Decimal('0')]
                previous_qty[key] = Decimal('0')
            if key in day_movements:
                stock[key][0] += day_movements[key][0]
                stock[key][1] += day_movements[key][1]

            qty = stock[key][0]
            if qty <= 0:
                always_present[key] = False

            if date(2025, 7, 1) <= d <= date(2025, 7, 10):
                if previous_qty[key] <= 0 and qty > 0 and key not in b_started:
                    b_started[key] = d
            elif d >= date(2025, 7, 11):
                if key in b_started and qty <= 0:
                    b_failed.add(key)

            previous_qty[key] = qty
        d += timedelta(days=1)

    eligible_a = {key for key, present in always_present.items() if present and stock[key][0] != 0 and stock[key][1] != 0}

    eligible_b = {
        key for key, started in b_started.items()
        if key not in b_failed and stock[key][0] != 0 and stock[key][1] != 0
    }

    return stock, eligible_a, eligible_b


def write_top10(path: Path, stock, eligible):
    by_location = defaultdict(list)
    for item_id, location_id in eligible:
        qty, cost = stock[(item_id, location_id)]
        by_location[location_id].append((cost, item_id, qty))

    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['item_id', 'location_id', 'trans_date', 'qty', 'cost_amount'])
        for location_id in sorted(by_location):
            rows = sorted(by_location[location_id], key=lambda x: (-x[0], x[1]))[:10]
            for cost, item_id, qty in rows:
                writer.writerow([item_id, location_id, '2025-07-31', format(qty, 'f'), format(cost, 'f')])


def main():
    parser = argparse.ArgumentParser(description='Calculate TOP-10 stock positions by location for task 02.')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()

    source = args.source.resolve()
    output = (args.output or (source / 'stock')).resolve()
    output.mkdir(parents=True, exist_ok=True)

    stock, eligible_a, eligible_b = calculate(source)
    write_top10(output / 'stock_2025_07_31_top10a.csv', stock, eligible_a)
    write_top10(output / 'stock_2025_07_31_top10b.csv', stock, eligible_b)

    print(f'top10a: {len(eligible_a)} eligible positions')
    print(f'top10b: {len(eligible_b)} eligible positions')
    print(f'Files written to: {output}')


if __name__ == '__main__':
    main()
