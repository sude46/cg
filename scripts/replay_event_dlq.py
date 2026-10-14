#!/usr/bin/env python3
"""重放事件总线死信队列 (event_bus:dead_letter)。

默认 dry-run：只统计死信条数与原因。
加 --apply：把可重放的事件（event_json 能解析）重置 retry_count 后重新入队
event_bus:queue，并从死信队列移除；解析失败的坏消息（raw）只报告、不动。

在 app 容器内运行（需要 Redis 连接）：
    docker exec -i weibo-app python scripts/replay_event_dlq.py
    docker exec -i weibo-app python scripts/replay_event_dlq.py --apply --limit 100
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from utils.redis_util import RedisClient

QUEUE = 'event_bus:queue'
DLQ = 'event_bus:dead_letter'


def run(apply: bool, limit) -> None:
    app = create_app()
    with app.app_context():
        conn = RedisClient.get_conn(for_write=True)
        if conn is None:
            print('Redis 未连接，退出')
            return

        items = conn.lrange(DLQ, 0, -1) or []
        print(f'死信队列共 {len(items)} 条')

        reasons = Counter()
        replayable = []      # (原始死信字符串, 事件dict)
        bad = []
        for raw in items:
            raw = raw.decode() if isinstance(raw, bytes) else raw
            try:
                item = json.loads(raw)
            except Exception:
                bad.append(raw)
                reasons['unparsable_item'] += 1
                continue
            reasons[item.get('reason', 'unknown')] += 1
            event_json = item.get('event_json')
            if not event_json:
                bad.append(raw)
                continue
            try:
                replayable.append((raw, json.loads(event_json)))
            except Exception:
                bad.append(raw)

        print('原因分布:', dict(reasons))
        print(f'可重放 {len(replayable)} 条，不可重放(坏消息) {len(bad)} 条')

        if not apply:
            print('dry-run（加 --apply 才真正重放）')
            return

        if limit is not None:
            replayable = replayable[:limit]
        n = 0
        for raw, event in replayable:
            event['retry_count'] = 0
            conn.lpush(QUEUE, json.dumps(event, ensure_ascii=False))
            conn.lrem(DLQ, 1, raw)
            n += 1
        print(f'已重放 {n} 条到 {QUEUE} 并从死信移除')


def main() -> None:
    parser = argparse.ArgumentParser(description='重放事件总线死信队列')
    parser.add_argument('--apply', action='store_true', help='真正重放（默认只 dry-run）')
    parser.add_argument('--limit', type=int, default=None, help='最多重放多少条')
    args = parser.parse_args()
    run(args.apply, args.limit)


if __name__ == '__main__':
    main()
