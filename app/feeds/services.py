import logging

from app.follows.cache import FollowCache
from app.follows.repositories import follow_repository
from app.posts.schemas import posts_schema
from core.metrics import FEED_OPERATIONS, REDIS_HIT_RATE

from .cache import ExploreCache, FeedCache
from .cursor import decode_cursor, encode_cursor
from .repository import FeedRepository

logger=logging.getLogger(__name__)

class FeedService:

    '''
    获取用户首页时间线
    采用推拉结合策略：
    普通用户（粉丝<1000）：推模式，发帖时主动推送到粉丝时间线
    大V用户（粉丝>=1000）：拉模式，粉丝读首页时实时聚合
        '''

    #每页默认条数
    DEFAULT_PER_PAGE=20
    #最大每页条数
    MAX_PRE_PAGE=100


    @classmethod
    def get_timeline(cls,user_id:int,cursor=None,limit:int=20):
        '''
        获取用户时间线（游标分页，推拉结合）
        策略：
        1.推来的：读用户 feed ZSet（普通作者 fanout + 自己的帖），带 score
        2.拉来的：读用户关注的大V outbox，与上面做多源归并
        3.feed 缓存未命中 -> DB keyset 兜底（JOIN Follow 已含大V）-> 回填
        cursor: 上一页返回的 next_cursor；首页传 None
        '''
        try:
            limit=min(max(1,limit),cls.MAX_PRE_PAGE)
            cur=decode_cursor(cursor)

            #===========第一步：读"推"来的 feed（带 score）============
            pushed=FeedCache.pull_feed_scored_by_cursor(user_id,cur,limit)

            #情况:feed 缓存未命中，走数据库 keyset 兜底
            if pushed is None:
                return cls._timeline_from_db(user_id,cur,limit)

            #===========第二步：读"拉"来的大V outbox============
            bigv_ids=cls._following_big_v_ids(user_id)

            #关注的大V过多时多路归并代价过大 -> 退化为DB兜底(JOIN已含全部大V),避免漏内容
            if len(bigv_ids)>FeedCache.MAX_MERGE_BIGV:
                logger.info(
                    f'用户{user_id}关注{len(bigv_ids)}个大V，超过归并上限'
                    f'{FeedCache.MAX_MERGE_BIGV}，本次退化为DB兜底'
                )
                return cls._timeline_from_db(user_id,cur,limit)

            pulled=[FeedCache.pull_outbox_scored_by_cursor(aid,cur,limit) for aid in bigv_ids]

            REDIS_HIT_RATE.labels(cache_type='feed').set(1)

            #===========第三步：多源归并去重、按 score 倒序============
            merged=cls._merge_scored(pushed,*pulled)
            if not merged:
                FEED_OPERATIONS.labels(action='timeline', result='success').inc()
                return {'items':[],'next_cursor':None,'has_more':False,'source':'empty'}

            has_more=len(merged)>limit
            page=merged[:limit]
            post_ids=[pid for pid,_ in page]
            next_cursor=(
                encode_cursor(page[-1][1],page[-1][0]) if has_more else None
            )
            posts=cls._get_posts_by_ids(post_ids)
            FEED_OPERATIONS.labels(action='timeline', result='success').inc()
            return {
                    'items':posts_schema.dump(posts),
                    'next_cursor':next_cursor,
                    'has_more':has_more,
                    'source':'hybrid' if any(pulled) else 'cache'
                }
        except Exception:
            FEED_OPERATIONS.labels(action='timeline', result='failed').inc()
            raise


    @classmethod
    def get_explore(cls,cursor=None,limit:int=20):
        '''
        获取广场（全站帖子，游标分页)
        策略与关注流一致:Redis Zset优先->miss走DB keyset->回填缓存
        '''
        try:
            limit=min(max(1,limit),cls.MAX_PRE_PAGE)
            cur=decode_cursor(cursor)
            result=ExploreCache.pull_by_cursor(cur,limit)
            if result is not None:
                cached_ids,next_cursor,has_more=result
                REDIS_HIT_RATE.labels(cache_type='explore_feed').set(1)
                if not cached_ids:
                    FEED_OPERATIONS.labels(action='explore', result='success').inc()
                    return {'items':[],'next_cursor':None,'has_more':False,'source':'empty'}
                posts=cls._get_posts_by_ids(cached_ids)
                FEED_OPERATIONS.labels(action='explore',result='success').inc()
                return {
                        'items':posts_schema.dump(posts),
                        'next_cursor':next_cursor,
                        'has_more':has_more,
                        'source':'cache',
                        }

            posts,has_more,nc=FeedRepository.get_explore_posts_cursor(cur,limit)
            REDIS_HIT_RATE.labels(cache_type='explore_feed').set(0)
            if posts:
                ExploreCache.batch_fill([
                    {'id':p.id,'created_at':p.created_at} for p in posts
                    ])
            FEED_OPERATIONS.labels(action='explore', result='success').inc()
            return {
                    'items':posts_schema.dump(posts),
                    'next_cursor':nc,
                    'has_more':has_more,
                    'source':'db',
                    }
        except Exception:
            FEED_OPERATIONS.labels(action='explore',result='failed').inc()
            raise




    @classmethod
    def _get_posts_by_ids(cls,post_ids:list[str]):
        '''
         根据Id列表批量查询帖子，并保持传入的顺序
        '''
        try:
            if not post_ids:
                return []
            posts=FeedRepository.get_posts_by_ids([int(pid)for pid in post_ids])


            #建立到D帖子的映射
            post_map={str(p.id):p for p in posts}

            #按原始顺序重组（并过滤掉数据库已删除/已下架的帖子）
            ordered_posts=[]
            for pid in post_ids:
                post=post_map.get(pid)
                if post:
                    ordered_posts.append(post)

             #如果顺序重组后发现数量不一致，说明有帖子被删除但缓存未清理
            if len(ordered_posts)!=len(post_ids):
                missing=set(post_ids)-set(post_map.keys())
                logger.warning(
                      f'缓存中有{len(missing)}个帖子载数据库中不存在或已删除,'
                      f'IDs:{missing},建议清理缓存'
                  )
            FEED_OPERATIONS.labels(action='get', result='success').inc()
            return ordered_posts
        except Exception:
            FEED_OPERATIONS.labels(action='get', result='failed').inc()
            raise


    @staticmethod
    def _merge_scored(*sources):
        '''
        多源 (member, score) 归并：按帖子ID去重后，按 score 倒序。
        各源都已按游标取到 limit+1 条，合并后 len>limit 即说明还有下一页。
        '''
        seen=set()
        merged=[]
        for rows in sources:
            for member,score in rows:
                if member in seen:
                    continue
                seen.add(member)
                merged.append((member,score))
        merged.sort(key=lambda item:item[1],reverse=True)
        return merged

    @classmethod
    def _following_big_v_ids(cls,user_id:int)->list[int]:
        '''用户关注的大V作者ID（读时据此拉取 outbox）'''
        following=FollowCache.get_following_ids(user_id)
        if following is None:
            following=follow_repository.get_following_ids(user_id)
        return FeedCache.filter_big_v(following)

    @classmethod
    def _timeline_from_db(cls,user_id:int,cur,limit:int):
        '''
        DB keyset 兜底：查关注流（JOIN Follow 已包含大V的帖）并回填缓存。
        用于 feed 缓存未命中、或关注大V过多触发归并降级两种场景。
        '''
        posts,has_more,nc=FeedRepository.get_following_posts_cursor(user_id,cur,limit)
        REDIS_HIT_RATE.labels(cache_type='feed').set(0)
        if posts:
            cls._backfill_cache(user_id,posts)
        elif cur is None:
            FeedCache.set_empty_cache(user_id)
        FEED_OPERATIONS.labels(action='timeline', result='success').inc()
        return {
                'items':posts_schema.dump(posts),
                'next_cursor':nc,
                'has_more':has_more,
                'source':'db'
            }

    @classmethod
    def _backfill_cache(cls,user_id:int,posts):
        '''
         数据库查询后回填redis缓存
        '''
        if not posts:
            return False
         #转换为缓存需要的格式
        cache_data=[{'id':p.id,'created_at':p.created_at} for p in posts]
        #批量写入缓存
        FeedCache.batch_fill_cache(user_id,cache_data)
    @classmethod
    def publish_post(cls,post_id:int,author_id:int,created_at):
        '''
         发布帖子后的Feed流处理（推模式入口）

         流程：
         加入作者自己的时间线
         写入作者 outbox（拉模式数据源，所有作者都写，与粉丝数无关）
         如果作者是普通用户，推送所有粉丝时间线
         如果是大V，跳过推送（粉丝读首页时从 outbox 拉取）

         '''
        #作者加入自己的时间线
        FeedCache.add_post_to_feed(author_id,post_id,created_at)
        #作者 outbox：所有作者都写，供关注他的大V走拉模式
        FeedCache.add_to_outbox(author_id,post_id,created_at)
        #全站广场同步写入(失败不影响推粉丝主流程)
        ExploreCache.add_post(post_id,created_at)

        # 先查缓存
        follower_ids = FollowCache.get_follower_ids(author_id)

        if follower_ids is None:
            # Cache miss：查 DB 从库 → 回填
            follower_ids = follow_repository.get_follower_ids(author_id)
            if follower_ids:
                FollowCache.preload_followers(author_id, follower_ids)
            logger.info(f'作者{author_id}粉丝缓存miss，从DB加载{len(follower_ids)}人')

        follower_count = len(follower_ids)

        #判断是否是大V，决定推/拉模式
        is_big_v=FeedCache.is_big_v(follower_count)

        if is_big_v:
            # 大V：不发推，登记到大V集合，粉丝读首页时从 outbox 拉取
            FeedCache.mark_big_v(author_id)
            logger.info(
                f'作者{author_id}是大V({follower_count}粉丝)，'
                f'帖子{post_id}使用拉模式'
            )
            return {
                'post_id': post_id,
                'mode': 'pull',
                'followers': follower_count,
                'pushed': 0
            }
        # 普通用户：粉丝数掉回阈值以下则取消大V标记；fanout 下沉 Celery feed 队列
        FeedCache.unmark_big_v(author_id)
        # 延迟导入：tasks.feed_tasks 顶层 import app.feeds.cache，顶层导入会形成循环
        from tasks.feed_tasks import async_push_to_followers
        try:
            async_push_to_followers.apply_async(
                args=(post_id, author_id, created_at),
                queue='feed',
                retry=True,
                retry_policy={'max_retries': 2, 'interval_start': 0.2, 'interval_step': 0.2},
            )
            return {
                'post_id': post_id,
                'mode': 'push_async',
                'followers': follower_count,
                'pushed': 0
            }
        except Exception as exc:
            # 入队失败兜底：降级为同步推送（宁可阻塞事件总线也不丢内容），并打指标告警
            FEED_OPERATIONS.labels(action='fanout', result='enqueue_failed').inc()
            logger.error(
                f'feed fanout 入队失败，降级同步推送 post={post_id},author={author_id}:{exc}'
            )
            result = FeedCache.push_to_followers(
                post_id=post_id,
                created_at=created_at,
                follower_ids=follower_ids,
                follower_count=follower_count
            )
            return {
                'post_id': post_id,
                'mode': 'push_fallback',
                'followers': follower_count,
                'pushed': result['pushed']
            }
    @classmethod
    def delete_post(cls,post_id:int,author_id:int):
        '''
         删除帖子后的Feed流清理

        **注意**：粉丝缓存清理是异步操作，可能有几秒延迟
        '''
        #从作者自己的时间线移除，并清作者 outbox
        FeedCache.remove_posts(author_id,post_id)
        FeedCache.remove_from_outbox(author_id,post_id)

        ExploreCache.remove_post(post_id)

        # 大V的帖从未 fanout 进粉丝 feed，无需遍历粉丝（回填产生的历史ID由读时软删过滤兜底）
        if FeedCache.filter_big_v([author_id]):
            logger.info(f'帖子{post_id}作者{author_id}为大V，跳过粉丝时间线清理')
            return {
                'post_id': post_id,
                'removed_from_author': True,
                'removed_from_followers': 'skipped_big_v',
                'total_followers': 0
            }

        #获取粉丝列表（用于清理他们的缓存）
        followers=FeedRepository.get_followers(author_id)

        follower_ids=[f.follower_id for f in followers]

        #同步清理粉丝缓存
        # 3. 同步清理粉丝缓存（小粉丝量时可直接执行）
        if len(follower_ids) <= 100:
            result = FeedCache.remove_post_from_all_followers(
                post_id, follower_ids
            )
        else:
            try:
                # 延迟导入：tasks.feed_tasks 顶层会 import app.feeds.cache，
                # 若此处放顶层 import 会与 app.feeds 形成循环，导致 Celery worker 启动失败。
                from tasks.feed_tasks import async_remove_post_from_followers
                async_remove_post_from_followers.delay(post_id,follower_ids)
                result={'removed_from':'async_queued','total_followers':len(follower_ids)}
            except ImportError:
                #Celery未配置时，同步执行前100个
                logger.warning('Celery未配置，同步清理前100个粉丝缓存')
                result=FeedCache.remove_post_from_all_followers(
                    post_id,follower_ids[:100]
                )

        return {
            'post_id': post_id,
            'removed_from_author': True,
            'removed_from_followers': result['removed_from'],
            'total_followers': len(follower_ids)
        }
    @classmethod
    def follow_user(cls, follower_id: int, followed_id: int) -> bool:
        '''
        用户关注某人后的处理

        需要清空关注者的时间线缓存（因为时间线内容变了）

        Args:
            follower_id: 关注者ID（执行关注操作的人）
            followed_id: 被关注者ID

        Returns:
            bool: 是否成功
        '''
        # 清空关注者的时间线缓存（下次读时会重新从数据库拉取，包含新关注的人的帖子）
        FeedCache.invalidate_feed(follower_id)

        logger.info(f'用户{follower_id}关注用户{followed_id}，时间线缓存已清空')
        return True
    @classmethod
    def unfollow_user(cls, follower_id: int, followed_id: int) -> bool:
        '''
        用户取关某人后的处理

        需要清空取关者的时间线缓存

        Args:
            follower_id: 取关者ID
            followed_id: 被取关者ID

        Returns:
            bool: 是否成功
        '''
        # 清空取关者的时间线缓存
        FeedCache.invalidate_feed(follower_id)

        logger.info(f'用户{follower_id}取关用户{followed_id}，时间线缓存已清空')
        return True
    @classmethod
    def refresh_user_feed(cls, user_id: int) -> dict:
        '''
        手动刷新用户时间线（用于后台管理或用户主动刷新）

        强制清空缓存并从数据库重新加载

        Args:
            user_id: 用户ID

        Returns:
            dict: 刷新结果
        '''
        # 清空缓存
        FeedCache.invalidate_feed(user_id)

        # 重新加载第一页
        result = cls.get_timeline(user_id, cursor=None, limit=cls.DEFAULT_PER_PAGE)

        return {
            'user_id': user_id,
            'refreshed': True,
            'loaded_posts': len(result['items']),
            'source': result['source']
        }












