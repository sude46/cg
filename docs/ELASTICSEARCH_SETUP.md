# Elasticsearch 搜索系统集成指南

本文档介绍如何在微博系统中集成 Elasticsearch，实现高性能全文搜索。

---

## 📋 目录

1. [快速开始](#快速开始)
2. [架构设计](#架构设计)
3. [核心功能](#核心功能)
4. [API 文档](#api-文档)
5. [管理命令](#管理命令)
6. [性能优化](#性能优化)
7. [故障排查](#故障排查)

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requiresments.txt
```

### 2. 启动 Elasticsearch

```bash
# 方式1：使用 Docker Compose（推荐）
docker-compose -f docker-compose.es.yml up -d

# 方式2：使用脚本安装中文分词器
bash scripts/setup_es.sh
```

### 3. 初始化索引

```bash
python manage_es.py init
```

### 4. 导入现有数据

```bash
python manage_es.py reindex
```

### 5. 验证搜索

```bash
python manage_es.py test
```

---

## 架构设计

### 数据流

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  用户操作    │────▶│  Flask API   │────▶│    MySQL        │
│ (发帖/点赞)  │     │              │     │  (主数据库)      │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
                           │ 双写同步
                           ▼
                    ┌──────────────┐
                    │Elasticsearch │
                    │  (搜索索引)   │
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   搜索查询    │
                    └──────────────┘
```

### 降级策略

当 ES 不可用时，系统自动降级到 MySQL LIKE 搜索：

```python
# ES 搜索失败时自动降级
if not es_client.is_available():
    return PostSearchService._fallback_db_search(...)
```

---

## 核心功能

### 1. 智能分词搜索

**中文分词（IK 分词器）**：
- `ik_max_word`: 细粒度分词（索引时使用）
- `ik_smart`: 智能分词（搜索时使用）

**示例**：
```
搜索词: "美食探店"
分词结果: ["美食", "探店"] / ["美食探店"]
匹配内容: "今天去了一家超棒的美食店探店..."
```

### 2. 高亮显示

搜索结果自动高亮匹配的关键词：

```json
{
  "content": "今天去了一家超棒的<em class=\"highlight\">美食</em>店<em class=\"highlight\">探店</em>...",
  "raw_content": "今天去了一家超棒的美食店探店..."
}
```

### 3. 多维度排序

| 排序方式 | 参数值 | 说明 |
|---------|--------|------|
| 相关度 | `relevance` | 默认，按匹配分数排序 |
| 时间 | `time` | 最新发布的优先 |
| 热度 | `hot` | 按热度分数排序 |

热度算法：
```python
hot_score = like_count + comment_count * 2 + time_bonus
```

### 4. 搜索建议（自动补全）

输入时实时提示相关搜索词（待实现）。

### 5. 热搜榜

实时计算热门搜索内容：

```
GET /api/posts/hot-searches
```

---

## API 文档

### 搜索帖子

```http
GET /api/posts/search?q={关键词}&page=1&per_page=20&sort=relevance
```

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词 |
| page | int | 否 | 页码，默认1 |
| per_page | int | 否 | 每页数量，默认20 |
| sort | string | 否 | 排序方式：relevance/time/hot |

**响应示例**：

```json
{
  "code": 200,
  "message": "搜索帖子成功",
  "data": {
    "posts": [
      {
        "id": 123,
        "content": "今天去了一家超棒的<em class=\"highlight\">美食</em>店...",
        "raw_content": "今天去了一家超棒的美食店...",
        "user": {
          "id": 456,
          "username": "美食博主"
        },
        "like_count": 100,
        "comment_count": 20,
        "created_at": "2024-01-15T10:30:00",
        "_score": 1.5
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 150,
      "total_pages": 8
    },
    "search_engine": "elasticsearch"
  }
}
```

### 获取热搜榜

```http
GET /api/posts/hot-searches?size=10
```

**响应示例**：

```json
{
  "code": 200,
  "message": "获取热搜榜成功",
  "data": {
    "hot_searches": [
      {"keyword": "美食", "score": 9999},
      {"keyword": "旅行", "score": 8888}
    ]
  }
}
```

---

## 管理命令

### 索引管理

```bash
# 创建索引
python manage_es.py init

# 删除索引（危险）
python manage_es.py delete

# 查看状态
python manage_es.py status
```

### 数据同步

```bash
# 全量重建索引
python manage_es.py reindex

# 测试搜索
python manage_es.py test
```

---

## 性能优化

### 1. 索引优化

```python
# 合理的分片数
'settings': {
    'number_of_shards': 3,      # 根据数据量调整
    'number_of_replicas': 1     # 副本数
}
```

### 2. 查询优化

- 使用 `filter` 代替 `must`（缓存优化）
- 限制返回字段
- 合理设置分页深度

### 3. 硬件建议

| 数据量 | 内存 | CPU | 磁盘 |
|--------|------|-----|------|
| < 100万 | 4GB | 2核 | SSD |
| 100万-1000万 | 8GB | 4核 | SSD |
| > 1000万 | 16GB+ | 8核+ | NVMe SSD |

---

## 故障排查

### ES 连接失败

```bash
# 检查服务状态
curl http://localhost:9200/_cluster/health

# 检查日志
docker logs weibo-es
```

### 搜索无结果

1. 检查索引是否存在：`python manage_es.py status`
2. 检查数据是否已同步：`python manage_es.py reindex`
3. 检查分词器是否正确安装

### 性能问题

```bash
# 查看慢查询
curl http://localhost:9200/_cluster/nodes/hot_threads

# 查看索引状态
curl http://localhost:9200/_cat/indices?v
```

---

## 常见问题

**Q: 为什么搜索结果没有高亮？**
A: 检查 highlight 配置，确保查询包含关键词。

**Q: 中文分词不正确？**
A: 确认 IK 分词器已安装：`docker exec weibo-es-cn bin/elasticsearch-plugin list`

**Q: 如何扩展 ES 集群？**
A: 修改 docker-compose.es.yml，添加更多 ES 节点，配置集群发现。

---

## 下一步

- [ ] 实现搜索建议自动补全
- [ ] 添加搜索历史记录
- [ ] 个性化搜索排序
- [ ] 搜索结果统计分析
