#!/bin/sh
# app 容器启动入口：先执行数据库迁移，成功后才启动应用。
# celery worker/beat 不使用本脚本（各自 command 直接启动，无需迁移）。
set -e

if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

echo "[entrypoint] 执行数据库迁移: flask db upgrade ..."
flask db upgrade

if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -f "$PROMETHEUS_MULTIPROC_DIR"/*.db
fi

# 防御：若上游未透传启动命令（$@ 为空），回退到镜像默认 gunicorn 命令
if [ $# -eq 0 ]; then
    echo "[entrypoint] 警告: 未接收到启动命令，回退到默认 gunicorn"
    set -- gunicorn -w 4 -k gthread --threads 8 -b 0.0.0.0:5000 --access-logfile - --error-logfile - -c gunicorn.conf.py wsgi:app
fi

echo "[entrypoint] 迁移完成，启动: $@"
exec "$@"
