#!/bin/bash
# 仅在 MySQL 数据目录【首次初始化】时执行一次（docker-entrypoint-initdb.d 机制）。
# 密码全部从环境变量读取（MYSQL_PASSWORD / REPL_PASS / MYSQL_EXPORTER_PASSWORD / MONITOR_PASS），
# 缺省值仅供本地演示；真实部署请通过 ALTER USER 轮换。
set -e

MASTER_HOST="weibo-mysql-master"
MASTER_PORT="3306"
REPL_USER="replicator"
REPL_PASS="${REPL_PASS:-repl_pass_123}"
APP_DB="weibo"
APP_USER="weibo"
APP_PASS="${MYSQL_PASSWORD:-123456}"
EXPORTER_PASS="${MYSQL_EXPORTER_PASSWORD:-exporter123}"
MONITOR_PASS="${MONITOR_PASS:-monitor123}"

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

# 主库的 CREATE USER 事件位于种子位点之前，不会随复制重放，需在从库手动建号。
# 注意：replicator/exporter 也必须在此建号，否则主库后续 ALTER USER 复制到从库
# 会因账号不存在而报 errno 1396，SQL 线程停摆（2026-10-09 轮换时踩过的坑）。
echo "[Replica Init] 创建应用/复制/监控/巡检账号..."
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    CREATE USER IF NOT EXISTS '$APP_USER'@'%' IDENTIFIED BY '$APP_PASS';
    GRANT ALL PRIVILEGES ON $APP_DB.* TO '$APP_USER'@'%';
    CREATE USER IF NOT EXISTS 'replicator'@'%' IDENTIFIED BY '$REPL_PASS';
    GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'%';
    CREATE USER IF NOT EXISTS 'exporter'@'%' IDENTIFIED BY '$EXPORTER_PASS' WITH MAX_USER_CONNECTIONS 3;
    GRANT PROCESS, REPLICATION CLIENT, SLAVE MONITOR, SELECT ON *.* TO 'exporter'@'%';
    CREATE USER IF NOT EXISTS 'monitor'@'%' IDENTIFIED BY '$MONITOR_PASS';
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
