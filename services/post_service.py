from app.posts.services import PostService as DomainPostService
import logging

logger = logging.getLogger(__name__)


class PostService:
    """兼容 facade：保持顶层旧签名并委派到 `app.posts.services.PostService`。

    对于旧签名中的 `title`/`status`，会把 `title` 与 `content` 合并为下层 `content`。"""

    @staticmethod
    def create_post(user_id: int, title: str, content: str, status: str = 'published'):
        merged_content = (title or '').strip() + '\n\n' + (content or '').strip()
        return DomainPostService.create_post(user_id=user_id, content=merged_content, image_url=None)

    @staticmethod
    def get_post(post_id: int):
        return DomainPostService.get_post(post_id)

    @staticmethod
    def get_user_posts(user_id: int, page: int = 1, per_page: int = 20):
        return DomainPostService.get_posts(page=page, per_page=per_page, user_id=user_id)

    @staticmethod
    def update_post(post_id: int, user_id: int, **kwargs):
        # Domain update_post accepts content and image_url
        content = kwargs.get('content')
        image_url = kwargs.get('image_url')
        return DomainPostService.update_post(post_id=post_id, user_id=user_id, content=content, image_url=image_url)

    @staticmethod
    def delete_post(post_id: int, user_id: int):
        return DomainPostService.delete_post(post_id, user_id)


