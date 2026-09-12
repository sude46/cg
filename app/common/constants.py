from enum import StrEnum

# ==================== 枚举类型（业务概念）====================

class NotificationType(StrEnum):
    """通知类型"""
    LIKE = "like"
    COMMENT = "comment"
    FOLLOW = "follow"
    SYSTEM = "system"
    REPLY = "reply"

class ResourceType(StrEnum):
    """资源类型"""
    POST = "post"
    COMMENT = "comment"
    USER = "user"
    REPLY = "reply"

class UserRole(StrEnum):
    """用户角色"""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# ==================== 业务限制（产品规则）====================
# 这些是与业务逻辑相关的限制，不是部署配置

# 内容长度限制（产品需求：帖子/评论不能超过多少字）
CONTENT_MIN_LENGTH = 1
CONTENT_MAX_LENGTH = 500  # 评论
POST_CONTENT_MAX_LENGTH = 1000  # 帖子

# 用户名/密码规则（产品需求：注册时的限制）
USERNAME_MIN_LENGTH = 4
USERNAME_MAX_LENGTH = 20
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 20

# 分页限制（产品需求：防止恶意请求）
PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100

# 文件上传限制
ALLOWED_IMAGE_TYPES = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


# ==================== 业务状态码（前后端约定）====================
# 注意：这是业务状态码，不是 HTTP 状态码

class BizCode:
    """业务状态码"""
    SUCCESS = 200
    CREATED = 201
    PARAM_ERROR = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    SERVER_ERROR = 500

    # 业务自定义码（10000+）
    USER_EXISTS = 10001
    EMAIL_EXISTS = 10002
    PASSWORD_WEAK = 10003
    ACCOUNT_LOCKED = 10004


# ==================== 缓存键前缀（业务命名空间）====================
# 这些只是命名空间前缀，实际的缓存配置在 config/

CACHE_KEY_PREFIX = {
    'user': 'user:',
    'post': 'post:',
    'notification': 'notification:',
    'session': 'session:',
}


