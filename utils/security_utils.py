from datetime import datetime, timedelta
from flask import current_app
from utils.redis_util import redis_client
from markupsafe import escape
import re


# 限流配置（可放到config/base.py中）
LOGIN_FAIL_THRESHOLD = 5  # 最大失败次数
LOCK_DURATION = 30  # 锁定时长（分钟）

# 允许的HTML标签（如需返回安全HTML，仅允许以下标签，其余转义）
ALLOWED_TAGS = ["a", "br", "em", "strong"]
# 允许的HTML属性
ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}

# 敏感信息脱敏配置
# Token脱敏：保留前6位和后四位，中间用*号填充
TOKEN_PATTERRN = re.compile(r"^([A-Za-z0-9]{6}).*[A-Za-z0-9]{4}$")
# 手机号脱敏：保留前三位和后四位，中间用*号填充
PHONE_PATTERN = re.compile(r"^(\d{3})\d{4}(\d{4})$")


def desensitize_token(token: str) -> str:
    """
    脱敏Token字符串
    :param token: 原始Token字符串
    :return: 脱敏后的Token字符串
    """
    if not isinstance(token, str) or len(token) < 10:
        return token
    match = TOKEN_PATTERRN.match(token)
    if match:
        return f"{match.group(1)}********{token[-4:]}"
    return f"{token[:6]}********{token[-4:]}"


def desensitize_password(password: str) -> str:
    """
    脱敏密码字符串
    :param password: 原始密码字符串
    :return: 脱敏后的密码字符串
    """
    if not isinstance(password, str) or len(password) < 2:
        return "*" * len(password)
    return f"{password[0]}{'*'*(len(password)-2)}{password[-1]}"


def desensitize_phone(phone: str) -> str:
    """
    脱敏手机号字符串
    :param phone: 原始手机号字符串
    :return: 脱敏后的手机号字符串
    """
    if not isinstance(phone, str) or len(phone) != 11:
        return phone
    match = PHONE_PATTERN.match(phone)
    if match:
        return f"{match.group(1)}****{match.group(2)}"
    return phone


def desensitize_data(data, sensitive_fields: list):
    """
    脱敏数据中的敏感字段
    :param data: 原始数据（字典或字符串）
    :param sensitive_fields: 需要脱敏的字段列表
    :return: 脱敏后的数据
    """
    if isinstance(data, dict):
        desensitized = {}
        for key, value in data.items():
            if key in sensitive_fields and isinstance(value, str):
                if "token" in key.lower():
                    desensitized[key] = desensitize_token(value)
                elif "password" in key.lower():
                    desensitized[key] = desensitize_password(value)
                elif "phone" in key.lower() or "mobile" in key.lower():
                    desensitized[key] = desensitize_phone(value)
                else:
                    desensitized[key] = "*" * len(value)
            else:
                desensitized[key] = value
        return desensitized
    elif isinstance(data, str):
        # 简单字符串脱敏（可根据需要扩展）
        for field in sensitive_fields:
            if field.lower() in data.lower():
                data = re.sub(r'(\b' + re.escape(field) + r'\b\s*:\s*)(\S+)', lambda m: m.group(1) + '*' * len(m.group(2)), data, flags=re.IGNORECASE)
        return data
    else:
        return data


def check_user_login_lock(user):  # 2. 移除参数注解中的 User 类型（核心改动2）
    """
    检查用户是否被锁定（基于用户表字段）
    :param user: 用户实例
    :return: (is_locked, message)：是否锁定、提示信息
    """
    # 3. 函数内部延迟导入 User 模型（核心改动3）
    from app.users.models import User
    if not user.lock_until:
        return False, ""
    
    # 锁定时间未过期
    if datetime.utcnow() < user.lock_until:
        remaining_minutes = int((user.lock_until - datetime.utcnow()).total_seconds() / 60)
        return True, f"账号已锁定，剩余{remaining_minutes}分钟后可重试"
    
    # 锁定时间已过期，解锁账号
    user.login_fail_count = 0
    user.lock_until = None
    return False, ""


def record_login_fail(user):  # 4. 移除参数注解中的 User 类型（核心改动4）
    """
    记录登录失败次数，达到阈值则锁定账号
    :param user: 用户实例
    """
    # 5. 函数内部延迟导入 User 模型（核心改动5）
    from app.users.models import User
    user.login_fail_count += 1
    if user.login_fail_count >= LOGIN_FAIL_THRESHOLD:
        # 锁定账号（30分钟）
        user.lock_until = datetime.utcnow() + timedelta(minutes=LOCK_DURATION)


def html_escape(content):
    """
    HTML转义（防止XSS）
    :param content: 待转义内容（字符串/字典/列表）
    :return: 转义后的内容
    """
    if isinstance(content, str):
        return escape(content)
    elif isinstance(content, dict):
        # 递归转义字典中的所有值
        return {k: html_escape(v) for k, v in content.items()}
    elif isinstance(content, list):
        # 递归转义列表中的所有元素
        return [html_escape(item) for item in content]
    else:
        # 非字符串类型，直接返回
        return content
