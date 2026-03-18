from app.comments.services import CommentService as DomainCommentService
import logging

logger = logging.getLogger(__name__)


class CommentService:
    """兼容 facade，保持原顶层签名并委派到 `app.comments.services.CommentService`。
    返回 shape 与原接口兼容（做最小适配）。
    """

    @staticmethod
    def create_comment(user_id: int, post_id: int, content: str):
        data = {'post_id': post_id, 'content': content}
        return DomainCommentService.create_comment(user_id, data)

    @staticmethod
    def get_post_comments(post_id: int, page: int = 1, per_page: int = 20):
        res = DomainCommentService.get_comments_by_post_id(post_id, page, per_page)
        return {'comments': res.get('items', []), 'pagination': res.get('pagination', {})}

    @staticmethod
    def update_comment(comment_id: int, user_id: int, content: str):
        data = {'content': content}
        return DomainCommentService.update_comment(comment_id, user_id, data)

    @staticmethod
    def delete_comment(comment_id: int, user_id: int):
        return DomainCommentService.delete_comment(comment_id, user_id)
