#!/bin/bash
set -e

echo "[Replica Init] 等待主库 binlog 就绪..."
until mysql -h weibo-mysql-master -P 3306 -u replicator -prepl_pass_123 -e "SHOW MASTER STATUS\G" 2>/dev/null | grep -q "File:"; do
    echo "[Replica Init] 主库未就绪，2秒后重试..."
    sleep 2
done

echo "[Replica Init] 主库就绪，配置复制..."

mysql -u root -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    CHANGE MASTER TO
        MASTER_HOST='weibo-mysql-master',
        MASTER_PORT=3306,
        MASTER_USER='replicator',
        MASTER_PASSWORD='repl_pass_123',
        MASTER_USE_GTID=slave_pos;
    START SLAVE;
EOSQL

echo "[Replica Init] 复制已启动，验证状态:"
mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "SHOW SLAVE STATUS\G" | grep -E "Slave_IO_Running|Slave_SQL_Running"
