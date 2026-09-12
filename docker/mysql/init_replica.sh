#!/bin/bash
set -e

MASTER_HOST="weibo-mysql-master"
MASTER_PORT="3306"
REPL_USER="replicator"
REPL_PASS="repl_pass_123"
APP_DB="weibo"
APP_USER="weibo"
APP_PASS="123456"

echo "[Replica Init] 等待主库就绪..."
until mysql -h "$MASTER_HOST" -P "$MASTER_PORT" -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SELECT 1" >/dev/null 2>&1; do
    echo "[Replica Init] 主库未就绪，2秒后重试..."
    sleep 2
done

# 重要：主库 binlog 会被 binlog_expire_logs_seconds 清理，空 GTID 从库用
# MASTER_USE_GTID=slave_pos 只能追增量、补不回存量。因此必须先全量导入并
# 记录一致位点，再启动复制。
echo "[Replica Init] 全量导入主库存量数据（带一致 GTID 位点）..."
mysqldump -h "$MASTER_HOST" -P "$MASTER_PORT" -uroot -p"$MYSQL_ROOT_PASSWORD" \
    --single-transaction --master-data=1 --gtid \
    --databases "$APP_DB" > /tmp/seed.sql
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" < /tmp/seed.sql
rm -f /tmp/seed.sql

# 主库的 CREATE USER 事件位于种子位点之前，不会随复制重放，需在从库手动建号
echo "[Replica Init] 创建应用账号与巡检账号..."
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    CREATE USER IF NOT EXISTS '$APP_USER'@'%' IDENTIFIED BY '$APP_PASS';
    GRANT ALL PRIVILEGES ON $APP_DB.* TO '$APP_USER'@'%';
    CREATE USER IF NOT EXISTS 'monitor'@'%' IDENTIFIED BY 'monitor123';
    GRANT REPLICATION CLIENT, SLAVE MONITOR ON *.* TO 'monitor'@'%';
    FLUSH PRIVILEGES;
EOSQL

echo "[Replica Init] 配置复制..."
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    CHANGE MASTER TO
        MASTER_HOST='$MASTER_HOST',
        MASTER_PORT=$MASTER_PORT,
        MASTER_USER='$REPL_USER',
        MASTER_PASSWORD='$REPL_PASS',
        MASTER_USE_GTID=slave_pos;
    START SLAVE;
EOSQL

echo "[Replica Init] 验证状态:"
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "SHOW SLAVE STATUS\G" | grep -E "Slave_IO_Running|Slave_SQL_Running"
