"""Feed 游标工具。

游标形如 '<精确 score>:<帖子ID>'：
- score 为 ZSet 中该条目的真实分数（含同秒 id 微偏移），开区间 `(score` 翻页不重不漏；
- 同时带上 id，供 DB keyset 在"同秒"场景下按 (created_at, id) 精确续页。
"""


def score_for(sec: int, post_id: int) -> float:
    """秒级时间戳 + id 微偏移，保证同秒帖子 score 唯一、排序近似时间。"""
    return sec + (post_id % 1000) / 1_000_000


def encode_cursor(score: float, post_id: int) -> str:
    return f'{float(score)}:{int(post_id)}'


def decode_cursor(cursor):
    """解析为 (score: float, post_id: int)；无效返回 None。"""
    if not cursor:
        return None
    try:
        score_s, _, id_s = str(cursor).partition(':')
        return float(score_s), int(id_s)
    except (TypeError, ValueError):
        return None
