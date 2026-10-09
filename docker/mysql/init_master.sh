#!/bin/bash
# 仅在 MySQL 数据目录【首次初始化】时执行一次（docker-entrypoint-initdb.d 机制）。
# 密码全部从环境变量读取（REPL_PASS / MYSQL_EXPORTER_PASSWORD），缺省值仅供本地演示；
# 真实部署请通过 ALTER USER 轮换（见 docs/部署改造记录）。
set -e

REPL_PASS="${REPL_PASS:-repl_pass_123}"
EXPORTER_PASS="${MYSQL_EXPORTER_PASSWORD:-exporter123}"

mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
CREATE USER IF NOT EXISTS 'replicator'@'%' IDENTIFIED BY '$REPL_PASS';
GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'%';

-- 监控专用账号（mysqld-exporter 最小权限）
CREATE USER IF NOT EXISTS 'exporter'@'%' IDENTIFIED BY '$EXPORTER_PASS' WITH MAX_USER_CONNECTIONS 3;
GRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'exporter'@'%';
FLUSH PRIVILEGES;
EOSQL
