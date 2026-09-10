#!/bin/sh
set -e

echo "[Sentinel] Waiting for redis-master..."
until redis-cli -h weibo-redis-master -p 6379 ping 2>/dev/null | grep -q PONG; do
  sleep 1
done

echo "[Sentinel] Resolving redis-master IP..."
REDIS_IP=$(getent hosts weibo-redis-master | awk '{print $1}')
if [ -z "$REDIS_IP" ]; then
  echo "[Sentinel] ERROR: cannot resolve weibo-redis-master"
  exit 1
fi
echo "[Sentinel] Resolved to $REDIS_IP"

echo "[Sentinel] Preparing config..."
mkdir -p /usr/local/etc/redis
cp /tmp/sentinel.conf /usr/local/etc/redis/sentinel.conf
sed -i "s/weibo-redis-master/$REDIS_IP/g" /usr/local/etc/redis/sentinel.conf

echo "[Sentinel] Starting..."
exec redis-sentinel /usr/local/etc/redis/sentinel.conf
