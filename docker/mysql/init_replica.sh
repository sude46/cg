#!/bin/bash
set -e

echo "[Replica Init] 等待主库 binlog 就绪..."

# 循环等待主库可连接且已生成 binlog
until mysql -h weibo-mysql-master -P 3306 -u replicator -prepl_pass_123 -e "SHOW MASTER STATUS\G" 2>/dev/null | grep -q "File:"; do
    echo "[Replica Init] 主库未就绪，2秒后重试..."
    sleep 2
done

echo "[Replica Init] 主库就绪，配置复制..."

# 使用 root 配置复制（需要 SUPER 权限）
mysql -u root -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    CHANGE REPLICATION SOURCE TO
        SOURCE_HOST='weibo-mysql-master',
        SOURCE_PORT=3306,
        SOURCE_USER='replicator',
        SOURCE_PASSWORD='repl_pass_123',
        SOURCE_AUTO_POSITION=1;
    START REPLICA;
EOSQL

echo "[Replica Init] 复制已启动，验证状态:"
mysql -u root -p"$MYSQL_ROOT_PASSWORD" -e "SHOW REPLICA STATUS\G" | grep -E "Replica_IO_Running|Replica_SQL_Running"


