import re

from marshmallow import ValidationError

from core.security import security_manager


def validate_username(username: str) -> bool:
    '''验证用户名格式'''
    return security_manager.validate_username(username)

def validate_email(email: str) -> bool:
    '''验证邮箱格式'''
    return security_manager.validate_email(email)

def validate_password(password: str) -> dict:
    '''验证密码强度，返回详细结果'''
    return security_manager.password_validator.validate(password)

def validate_password_simple(password: str) -> bool:
    '''简单密码验证（只返回是否通过）'''
    return security_manager.password_validator.validate(password)['is_valid']

def validate_password_complexity(password: str) -> None:
    '''验证密码复杂度，抛出异常说明不符合要求'''
    validation = security_manager.password_validator.validate(password)
    if not validation['is_valid']:
        raise ValidationError(f"密码不符合要求: {validation['issues']}")


def validate_content_length(content: str, max_length: int = 500, min_length: int = 1) -> dict:
    '''验证内容长度'''
    if not content:
        return {'is_valid': False, 'error': '内容不能为空'}
    if len(content) < min_length:
        return {'is_valid': False, 'error': f'内容长度不能少于{min_length}字符'}
    if len(content) > max_length:
        return {'is_valid': False, 'error': f'内容长度不能超过{max_length}字符'}
    return {'is_valid': True, 'error': None}


def validate_image_url(url: str) -> dict:
    '''验证图片URL格式'''
    if not url:
        return {'is_valid': False, 'error': 'URL不能为空'}
    # 简单的URL格式验证
    url_pattern = re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE)
    if not url_pattern.match(url):
        return {'is_valid': False, 'error': '无效的URL格式'}
    # 验证图片扩展名
    allowed_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    if not url.lower().endswith(allowed_extensions):
        return {'is_valid': False, 'error': 'URL必须以图片格式结尾(jpg/png/gif/webp/bmp)'}
    return {'is_valid': True, 'error': None}

