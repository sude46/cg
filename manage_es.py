#!/usr/bin/env python3
"""
Elasticsearch 管理脚本
用于索引管理、数据迁移、性能测试等

用法：
    python manage_es.py init          # 初始化索引
    python manage_es.py reindex       # 全量重建索引
    python manage_es.py status        # 查看 ES 状态
    python manage_es.py test          # 测试搜索
    python manage_es.py delete        # 删除索引（危险！）
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from services.search import PostSearchService, PostDocument,es_client


def init_index():
    """创建索引"""
    print(" 创建 Elasticsearch 索引...")
    
    if not es_client.is_available():
        print(" ES 不可用，请检查配置")
        return
    
    success = PostDocument.create_index()
    if success:
        print(f" 索引 {PostDocument.get_index_name()} 创建成功")
    else:
        print("索引创建失败")


def reindex_all():
    """全量重建索引"""
    print("开始全量重建索引...")
    
    if not es_client.is_available():
        print(" ES 不可用，请检查配置")
        return
    
    # 确认操作
    confirm = input("这将删除现有索引并重新索引所有帖子，确认吗？ [y/N]: ")
    if confirm.lower() != 'y':
        print("操作已取消")
        return
    
    success, failed = PostSearchService.reindex_all_posts(batch_size=100)
    
    print(f"\n 重建完成：")
    print(f"   成功: {success}")
    print(f"   失败: {failed}")


def check_status():
    """检查 ES 状态"""
    print("Elasticsearch 状态检查\n")
    
    if not es_client.is_available():
        print(" ES 连接失败")
        return
    
    client = es_client.client
    
    # 集群健康
    health = client.cluster.health()
    print(f"集群状态: {health['status']}")
    print(f"节点数: {health['number_of_nodes']}")
    print(f"活跃分片: {health['active_primary_shards']}")
    
    # 索引信息
    if client.indices.exists(index=PostDocument.INDEX_NAME):
        stats = client.indices.stats(index=PostDocument.get_index_name())
        doc_count = stats['indices'][PostDocument.INDEX_NAME]['total']['docs']['count']
        store_size = stats['indices'][PostDocument.INDEX_NAME]['total']['store']['size_in_bytes']
        
        print(f"\n索引: {PostDocument.INDEX_NAME}")
        print(f"文档数: {doc_count}")
        print(f"存储大小: {store_size / 1024 / 1024:.2f} MB")
    else:
        print(f"\n索引 {PostDocument.INDEX_NAME} 不存在")


def test_search():
    """测试搜索功能"""
    print("测试搜索功能\n")
    
    if not es_client.is_available():
        print(" ES 不可用")
        return
    
    # 测试不同查询
    test_queries = [
        "美食",
        "旅行",
        "编程",
    ]
    
    for query in test_queries:
        print(f"\n搜索: '{query}'")
        posts, total = PostDocument.search(query, page=1, per_page=5)
        print(f"  找到 {total} 条结果")
        for post in posts[:3]:
            content = post.get('highlight_content', post['content'])[:50]
            print(f"  - {content}... (ID: {post['id']})")


def delete_index():
    """删除索引（危险操作）"""
    print("🗑️ 删除索引")
    
    if not es_client.is_available():
        print("  ES 不可用")
        return
    
    # 双重确认
    print(f"  即将删除索引: {PostDocument.INDEX_NAME}")
    confirm1 = input("确认删除? [yes/no]: ")
    if confirm1 != 'yes':
        print("操作已取消")
        return
    
    confirm2 = input("再次确认? [DELETE]: ")
    if confirm2 != 'DELETE':
        print("操作已取消")
        return
    
    success = PostDocument.delete_index()
    if success:
        print(" 索引已删除")
    else:
        print("删除失败")


def show_help():
    """显示帮助"""
    print(__doc__)


def main():
    # 创建应用上下文
    app = create_app()
    
    with app.app_context():
        if len(sys.argv) < 2:
            show_help()
            return
        
        command = sys.argv[1]
        
        commands = {
            'init': init_index,
            'reindex': reindex_all,
            'status': check_status,
            'test': test_search,
            'delete': delete_index,
            'help': show_help,
        }
        
        if command in commands:
            commands[command]()
        else:
            print(f"未知命令: {command}")
            show_help()


if __name__ == '__main__':
    main()
