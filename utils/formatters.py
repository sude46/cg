import re

TOKEN_PATTERN = re.compile(r"^([A-Za-z0-9]{6}).*[A-Za-z0-9]{4}$")
PHONE_PATTERN = re.compile(r"^(\d{3})\d{4}(\d{4})$")


def desensitize_token(token: str) -> str:
    """脱敏Token：保留前6位和后4位"""
    if not isinstance(token, str) or len(token) < 10:
        return token
    match = TOKEN_PATTERN.match(token)
    if match:
        return f"{match.group(1)}********{token[-4:]}"
    return f"{token[:6]}********{token[-4:]}"


def desensitize_password(password: str) -> str:
    """脱敏密码：只显示首尾"""
    if not isinstance(password, str) or len(password) < 2:
        return "*" * len(password)
    return f"{password[0]}{'*' * (len(password) - 2)}{password[-1]}"


def desensitize_phone(phone: str) -> str:
    """脱敏手机号：保留前3位和后4位"""
    if not isinstance(phone, str) or len(phone) != 11:
        return phone
    match = PHONE_PATTERN.match(phone)
    if match:
        return f"{match.group(1)}****{match.group(2)}"
    return phone


def desensitize_data(data: dict, sensitive_fields: list = None) -> dict:
    """
    脱敏字典中的敏感字段
    """
    if sensitive_fields is None:
        sensitive_fields = ['password', 'token', 'access_token', 'refresh_token', 'phone']
    
    result = {}
    for key, value in data.items():
        if key in sensitive_fields:
            if 'token' in key.lower():
                result[key] = desensitize_token(value) if isinstance(value, str) else value
            elif 'password' in key.lower():
                result[key] = desensitize_password(value) if isinstance(value, str) else value
            elif 'phone' in key.lower():
                result[key] = desensitize_phone(value) if isinstance(value, str) else value
            else:
                result[key] = '***'
        else:
            result[key] = value
    return result