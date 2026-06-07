from .cache import FeedCache
from app.follows.cache import FollowCache
from app.follows.repositories import follow_repository
import logging
from typing import List,Optional 
from tasks.feed_tasks import async_remove_post_from_followers
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
    def get_timeline(cls,user_id:int,page:int=1,per_page:int=20):
        '''
        获取用户时间线
        策略：
        1.先读redis缓存
        2.缓存命中->批量查询数据库->按缓存顺序排序->返回
        3.缓存未命中->数据库拉取->回填缓存->返回

        '''
        #参数校验
        page=max(1,page)
        per_page=min(max(1,per_page),cls.MAX_PRE_PAGE)

        #===========第一步：尝试从Redist拉取============
        cached_ids=FeedCache.pull_feed(user_id,page,per_page)

        #情况1：缓存命中且有数据
        if cached_ids is not None and len(cached_ids)>0:
            posts=cls._get_posts_by_ids(cached_ids)
            return {
                    'items':posts,
                    'source':'cache',
                    'total':len(posts),
                    'page':page,
                    'has_more':len(cached_ids)>=per_page
                }
        #情况2 ：缓存命中但为空列表（用户未关注任何人，或关注的人都没发帖）
        if cached_ids is not None and len(cached_ids)==0:
            return {
                    'items':[],
                    'source':'empty',
                    'total':0,
                    'page':page,
                    'has_more':False
                }
        #情况3：缓存未命中，走数据库拉取
        result=cls._pull_from_database(user_id,page,per_page)

        #回填缓存
        if result['items']:
                cls._backfill_cache(user_id,result['items'])
        else:
                #数据库也没有，设置空缓存标记防穿透
                FeedCache.set_empty_cache(user_id)
        return result
        



    @classmethod
    def _get_posts_by_ids(cls,post_ids:List[str]):
        '''
         根据Id列表批量查询帖子，并保持传入的顺序
        '''
        if not post_ids:
            return []
        posts=FeedRepository.get_posts_by_ids([int(pid)for pid in post_ids])


        #建立到D帖子的映射
        post_map={str(p.id):p for p in posts}

        #按原始顺序重组（并过滤掉数据库已删除/已下架的帖子）
        ordered_posts=[]
        for pid in post_ids:
            post=post=post_map.get(pid)
            if post:
                ordered_posts.append(post)
        
         #如果顺序重组后发现数量不一致，说明有帖子被删除但缓存未清理
        if len(ordered_posts)!=len(post_ids):
            missing=set(post_ids)-set(post_map.keys()) 
            logger.warning(
                  f'缓存中有{len(missing)}个帖子载数据库中不存在或已删除,'
                  f'IDs:{missing},建议清理缓存' 
              )
        return ordered_posts
    
    @classmethod
    def _pull_from_database(cls,user_id:int,page:int,per_page:int=20):
        '''
         从数据库实时拉去关注用户的帖子（拉模式核心）
        '''
        offset=(page-1)*per_page
        posts, total = FeedRepository.get_following_posts(
            user_id=user_id,
            offset=offset,
            limit=per_page
        )
        has_more=len(posts)>=per_page
        return {
            'items': posts,
            'source': 'db',
            'total': total,
            'page': page,
            'has_more': has_more
        }
    @classmethod
    def _backfill_cache(cls,user_id:int,posts):
        '''
         数据库查询后回填redis缓存
        '''
        if not posts:
            return False
         #转换为缓存需要的格式
        cache_data=[]
        for post in posts:
              cache_data.append({
                   'id':post.id,
                   'created_at':post.created_at
              })
        #批量写入缓存
        FeedCache.batch_fill_cache(user_id,cache_data)
    @classmethod
    def publish_post(cls,post_id:int,author_id:int,created_at):
        '''
         发布帖子后的Feed流处理（推模式入口）

         流程：
         加入作者自己的时间线
         如果作者时普通股用户，推送所有粉丝时间线
         如果是大V，跳过推送（粉丝都是走拉模式）

        '''
        #作者加入自己的时间线
        FeedCache.add_post_to_feed(author_id,post_id,created_at)

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
             # 大V：不发推，直接返回
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
        # 普通用户：推送到所有粉丝
        result = FeedCache.push_to_followers(
            post_id=post_id,
            created_at=created_at,
            follower_ids=follower_ids,
            follower_count=follower_count
        )
        
        return {
            'post_id': post_id,
            'mode': 'push',
            'followers': follower_count,
            'pushed': result['pushed']
        }
    @classmethod
    def delete_post(cls,post_id:int,author_id:int):
        '''
         删除帖子后的Feed流清理

        **注意**：粉丝缓存清理是异步操作，可能有几秒延迟         
        '''
        #从做着自己的时间线移除
        FeedCache.remove_posts(author_id,post_id)

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
        result = cls.get_timeline(user_id, page=1, per_page=cls.DEFAULT_PER_PAGE)
        
        return {
            'user_id': user_id,
            'refreshed': True,
            'loaded_posts': len(result['items']),
            'source': result['source']
        }
    
    
        
             







        