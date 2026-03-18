import re

# -------------------------- 分页配置 --------------------------
PAGE_SIZE = 20  # 默认每页数据量
MAX_PAGE_SIZE = 100  # 最大每页数据量（防止恶意请求拖垮服务器）

# -------------------------- 枚举类型常量 --------------------------
# 通知类型（与 notifications 模块 Notification.type 对应）
NOTIFICATION_TYPES = {
    "LIKE": "like",  # 点赞通知
    "COMMENT": "comment",  # 评论通知
    "FOLLOW": "follow",  # 关注通知
    "SYSTEM": "system",  # 系统通知
    "REPLY": "reply"  # 回复通知
}

# 资源类型（与 notifications 模块 Notification.resource_type 对应）
RESOURCE_TYPES = {
    "POST": "post",  # 帖子资源
    "COMMENT": "comment",  # 评论资源
    "USER": "user",  # 用户资源（如关注）
    "REPLY": "reply"  # 回复资源
}

# 用户角色（与 users 模块 User.role 对应）
USER_ROLES = {
    "USER": "user",  # 普通用户
    "ADMIN": "admin",  # 管理员
    "SUPER_ADMIN": "super_admin"  # 超级管理员
}

# -------------------------- 正则表达式常量 --------------------------
REGEX_PHONE = re.compile(r'^1[3-9]\d{9}$')  # 中国大陆手机号（11位，以13-19开头）
REGEX_EMAIL = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')  # 邮箱（支持主流格式）
REGEX_USERNAME = re.compile(r'^[a-zA-Z0-9_]{4,20}$')  # 用户名（4-20位，字母、数字、下划线）
REGEX_PASSWORD = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,20}$')  # 密码（8-20位，含大小写、数字、特殊字符）

# -------------------------- 业务限制常量 --------------------------
CONTENT_MIN_LENGTH = 1  # 内容最小长度（评论、帖子等）
CONTENT_MAX_LENGTH = 500  # 内容最大长度（防止垃圾内容刷屏）
USERNAME_MIN_LENGTH = 4  # 用户名最小长度
USERNAME_MAX_LENGTH = 20  # 用户名最大长度
PASSWORD_MIN_LENGTH = 8  # 密码最小长度
PASSWORD_MAX_LENGTH = 20  # 密码最大长度

# -------------------------- JWT 配置常量 --------------------------
JWT_ACCESS_TOKEN_EXPIRES_MINUTES = 30  # Access Token 过期时间（分钟）
JWT_REFRESH_TOKEN_EXPIRES_DAYS = 7  # Refresh Token 过期时间（天）

# -------------------------- 缓存键前缀 --------------------------
# 用于 Redis 等缓存服务，避免键名冲突
CACHE_KEY_USER = "user:"  # 用户信息缓存键前缀（如 user:123 表示 ID=123 的用户）
CACHE_KEY_POST = "post:"  # 帖子信息缓存键前缀（如 post:456 表示 ID=456 的帖子）
CACHE_KEY_NOTIFICATION_UNREAD_COUNT = "notification:unread:"  # 未读通知数缓存键前缀（如 notification:unread:123 表示用户123的未读通知数）

# -------------------------- 业务状态码 --------------------------
# 与前端约定的状态码，便于统一处理响应
STATUS_SUCCESS = 200  # 操作成功
STATUS_ERROR = 500  # 操作失败
STATUS_VALIDATION_ERROR = 400  # 参数验证失败
STATUS_NOT_FOUND = 404  # 资源不存在
STATUS_PERMISSION_DENIED = 403  # 权限不足
STATUS_UNAUTHORIZED = 401  # 未认证



