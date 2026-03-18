
from app.follows.services import FollowService as DomainFollowService
import logging

logger = logging.getLogger(__name__)


class FollowService:
    """兼容 facade：委派到 `app.follows.services.FollowService` 并适配返回格式。"""

    @staticmethod
    def follow_user(follower_id: int, followed_id: int):
        return DomainFollowService.follow_user(follower_id, followed_id)

    @staticmethod
    def unfollow_user(follower_id: int, followed_id: int):
        return DomainFollowService.unfollow_user(follower_id, followed_id)

    @staticmethod
    def get_followers(user_id: int, page: int = 1, per_page: int = 20):
        res = DomainFollowService.get_followers(user_id, page, per_page)
        # domain 返回 {'follows': [...]}
        return {'followers': res.get('follows', []), 'pagination': res.get('pagination', {})}

    @staticmethod
    def get_following(user_id: int, page: int = 1, per_page: int = 20):
        res = DomainFollowService.get_following(user_id, page, per_page)
        return {'following': res.get('follows', []), 'pagination': res.get('pagination', {})}

    @staticmethod
    def get_mutual_follows(user_id: int):
        res = DomainFollowService.get_mutual_follows(user_id)
        # domain 返回 'mutual_users'
        return {'mutuals': res.get('mutual_users', [])}

    @staticmethod
    def is_following(follower_id: int, followed_id: int) -> bool:
        return DomainFollowService.is_following(follower_id, followed_id)
    def unfollow_user(follower_id:int,followed_id:int):

