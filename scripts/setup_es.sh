#!/bin/bash
# scripts/setup_es.sh
# Elasticsearch 环境初始化脚本

echo "🚀 启动 Elasticsearch 环境..."

# 1. 启动容器
docker-compose -f docker-compose.es.yml up -d

# 2. 等待 ES 启动
echo "⏳ 等待 Elasticsearch 启动..."
until curl -s http://localhost:9200/_cluster/health | grep -q "status"; do
    sleep 2
    echo "  等待中..."
done

echo "✅ Elasticsearch 已启动"

# 3. 检查集群健康状态
curl -s http://localhost:9200/_cluster/health?pretty

# 4. 安装中文分词插件 (IK 分词器)
echo "📦 安装 IK 中文分词器..."
docker exec -it weibo-es-cn bash -c \
    "bin/elasticsearch-plugin install https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v8.11.0/elasticsearch-analysis-ik-8.11.0.zip" || true

# 5. 重启以加载插件
docker-compose -f docker-compose.es.yml restart elasticsearch-cn

echo "🎉 Elasticsearch 环境就绪！"
echo "  - ES API: http://localhost:9200"
echo "  - Kibana: http://localhost:5601"
echo "  - ES with IK: http://localhost:9201"
