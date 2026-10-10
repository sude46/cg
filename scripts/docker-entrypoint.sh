#!/bin/sh
# app 容器启动入口：先执行数据库迁移，成功后才启动应用。
# celery worker/beat 不使用本脚本（各自 command 直接启动，无需迁移）。
set -e

echo "[entrypoint] 执行数据库迁移: flask db upgrade ..."
flask db upgrade

# 防御：若上游未透传启动命令（$@ 为空），回退到镜像默认 gunicorn 命令
if [ $# -eq 0 ]; then
    echo "[entrypoint] 警告: 未接收到启动命令，回退到默认 gunicorn"
    set -- gunicorn -w 4 -k gthread --threads 2 -b 0.0.0.0:5000 --access-logfile - --error-logfile - wsgi:app
fi

echo "[entrypoint] 迁移完成，启动: $@"
exec "$@"
