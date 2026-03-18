from typing import Optional
import logging
from core.database import db  # ✅ 统一从 core.database 导入
from app.users.models import User
from app.common.database import pagination_utils
from .schemas import UserListSchema

logger = logging.getLogger(__name__)

class UserRepository:
    """用户仓储：封装 User 模型的所有数据库访问."""

    @staticmethod
    def get_by_id(user_id: int):
        # ✅ 使用 db.session.get 替代已弃用的 Query.get
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_username(username: str):
        return User.query.filter_by(username=username).first()

    @staticmethod
    def get_by_email(email: str):
        return User.query.filter_by(email=email).first()

    @staticmethod
    def create_user(**fields):
        user = User(**fields)
        db.session.add(user)
        return user

    @staticmethod
    def list_users(page: int = 1, size: int = 20) -> dict:
        """统一分页查询用户列表."""
        try:
            query = User.query.order_by(User.id.desc())
            page_data = pagination_utils.paginate(query, page=page, per_page=size)
            list_schema = UserListSchema()
            return list_schema.dump({
                'items': page_data.items,
                'total': page_data.total,
                'page': page_data.page,
                'size': page_data.per_page,
                'pages': page_data.pages
            })
        except Exception as e:
            logger.error(f"分页查询用户列表失败: {e}")
            raise

user_repository = UserRepository()
