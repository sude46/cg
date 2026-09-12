#!/usr/bin/env python3
"""从库复制巡检脚本（供 cron 调用，异常时退出码非 0 便于告警）。

检查 Slave_IO_Running / Slave_SQL_Running / Seconds_Behind_Master / Last_Error。
默认连宿主映射端口 127.0.0.1:3307（从库），可用环境变量覆盖：

    REPLICA_CHECK_HOST / REPLICA_CHECK_PORT / MYSQL_USER / MYSQL_PASSWORD
    REPLICA_MAX_LAG_SECONDS (默认 60)

示例 crontab（每分钟）：
    * * * * * cd /home/app/weibo-platform && venv/bin/python scripts/check_replica.py >> logs/replica_check.log 2>&1
"""
import os
import sys

import pymysql

HOST = os.getenv('REPLICA_CHECK_HOST', '127.0.0.1')
PORT = int(os.getenv('REPLICA_CHECK_PORT', '3307'))
USER = os.getenv('REPLICA_CHECK_USER', 'monitor')
PASSWORD = os.getenv('REPLICA_CHECK_PASSWORD', 'monitor123')
MAX_LAG = int(os.getenv('REPLICA_MAX_LAG_SECONDS', '60'))


def main() -> int:
    try:
        conn = pymysql.connect(
            host=HOST, port=PORT, user=USER, password=PASSWORD, connect_timeout=5
        )
    except Exception as e:
        print(f'[FAIL] 无法连接从库 {HOST}:{PORT}: {e}')
        return 1

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute('SHOW SLAVE STATUS')
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        print('[FAIL] SHOW SLAVE STATUS 为空：复制未配置（检查数据卷是否存在导致 init 被跳过）')
        return 1

    io = row.get('Slave_IO_Running')
    sql = row.get('Slave_SQL_Running')
    lag = row.get('Seconds_Behind_Master')
    err = row.get('Last_Error')

    problems = []
    if io != 'Yes':
        problems.append(f'Slave_IO_Running={io}')
    if sql != 'Yes':
        problems.append(f'Slave_SQL_Running={sql}')
    if lag is not None and lag > MAX_LAG:
        problems.append(f'Seconds_Behind={lag}s(>{MAX_LAG})')
    if err:
        problems.append(f'Last_Error={err}')

    if problems:
        print('[FAIL] 从库复制异常: ' + '; '.join(problems))
        return 1

    print(f'[OK] 从库复制正常 IO={io} SQL={sql} lag={lag}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
