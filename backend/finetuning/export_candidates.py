"""Read-only export for human review. This does not train a model."""
import argparse
import json
from pathlib import Path
import sqlite3


def export(database: Path, output: Path) -> int:
    # mode=ro also prevents silently creating an empty database on a wrong path.
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('''SELECT id, created_at, intersection_id, status, context,
            strategy, weight_ns, weight_ew, duration_min, reason
            FROM llm_decisions WHERE status IN ('APPROVED', 'APPLIED')
            ORDER BY created_at, id''').fetchall()
    candidates = []
    for row in rows:
        context = json.loads(row['context'])
        if not isinstance(context, dict) or not context:
            continue
        target = {key: row[key] for key in
                  ('strategy', 'weight_ns', 'weight_ew', 'duration_min', 'reason')}
        if any(value is None for value in target.values()):
            continue
        candidates.append({
            'source_id': row['id'], 'created_at': row['created_at'],
            'intersection_id': row['intersection_id'], 'source_status': row['status'],
            'reviewed': False, 'context': context, 'target': target,
            'review_note': 'Kiểm tra số liệu, chiến lược và trọng số trước khi chấp nhận nhãn.',
        })
    if not candidates:
        print('Không có dữ liệu ứng viên. Không tạo tập huấn luyện giả.')
        return 0
    # Exclusive creation avoids overwriting an already reviewed dataset.
    with output.open('x', encoding='utf-8') as stream:
        for candidate in candidates:
            stream.write(json.dumps(candidate, ensure_ascii=False, allow_nan=False) + '\n')
    print(f'Đã xuất {len(candidates)} mẫu CHƯA DUYỆT vào {output}')
    return len(candidates)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.database, args.output)
