from app.likes.services import LikeService as DomainLikeService
import logging

logger = logging.getLogger(__name__)


class LikeService:
    """兼容 facade：将旧签名适配到 `app.likes.services.LikeService`。"""

    @staticmethod
    def like_post(user_id: int, post_id: int) -> dict:
        res = DomainLikeService.create_like(user_id=user_id, post_id=post_id)
        # 下游返回 like dict，保持旧接口返回 shape
        if isinstance(res, dict):
            return {'message': '点赞成功', 'like': res}
        return res

    @staticmethod
    def unlike_post(user_id: int, post_id: int):
        return DomainLikeService.delete_like(user_id=user_id, post_id=post_id)

    @staticmethod
    def get_user_likes(user_id: int, page: int = 1, per_page: int = 20):
        res = DomainLikeService.get_user_likes(user_id=user_id, page=page, per_page=per_page)
        # domain 返回 {'items','pagination'}，适配为旧的 keys
        return {'likes': res.get('items', []), 'pagination': res.get('pagination', {})}

