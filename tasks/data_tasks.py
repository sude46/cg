from celery import shared_task
from sqlalchemy import text
from app.posts.cache import PostCache
from  core import db
import logging
from datetime import datetime,timezone,timedelta

logger=logging.getLogger(__name__)


@shared_task
def calculate_hot_posts(periode:str='daily',limit:int=1000):
    '''
    定时计算热帖帮（每小时执行，适合小项目）
    用游标/分页查DB,避免全量加载内存
    '''

    try:
        since=datetime.now(timezone.utc)-timedelta(days=1)  #只查二十四小时

        #游标分页查询，避免OOM
        batch_size=500
        offset=0
        all_posts=[]
        while True:
            sql=text(
                """
                SELECT id, like_count, comment_count, created_at 
                FROM posts 
                WHERE deleted_at IS NULL 
                  AND is_published = TRUE
                  AND created_at > :since
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """
            )
            rows=db.session.execute(sql,{
                'since':since,
                'limit':batch_size,
                'offset':offset
            })

            if not rows:
                break

            for row in rows:
                score=PostCache.calc_hot_score(
                    like_count=row.like_count,
                    comment_count=row.comment_count,
                    created_at=row.created_at 
                )
                all_posts.append({'post_id': row.id, 'score': score})

            offset+=batch_size

            #安全阀：最多查5万条，防止异常数据爆炸
            if offset>=50000:
                logger.warning('[HotPosts]候选集超过5万，截断')
                break

        #按分数倒序，取Top limit
        all_posts.sort(key=lambda x:x['score'],reverser=True)
        top_posts=all_posts[:limit]

        PostCache.update_hot_posts(top_posts,period=periode)
        logger.info(f'[HotPosts]计算完成，候选集{len(all_posts)}条，入榜{len(top_posts)}条')
        return {'status': 'success', 'candidate_count': len(all_posts), 'top_count': len(top_posts)}
    except Exception as e:
        logger.error(f'[HotPosts]计算失败:{e}')
        return {'status':'failed','error':str(e)}
    