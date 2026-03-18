import os
import secrets
import hashlib
import re
from typing import Optional, Tuple, Union
from datetime import datetime, timedelta
import jwt
import bcrypt  # 新增：引入bcrypt库（如需使用bcrypt加密）
from flask import current_app

# 配置项：抽离安全参数，便于生产环境调整
SECURITY_CONFIG = {
    "pbkdf2_iterations": 200000,  # 提升迭代次数，增强加密强度
    "bcrypt_rounds": 14,  # 指定bcrypt rounds为14（生产环境推荐值）
    "access_token_expire_minutes": 15,  # access_token过期时间：15分钟
    "refresh_token_expire_days": 7,  # refresh_token过期时间：7天
    "reset_token_expire_hours": 1,  # 重置令牌过期时间：1小时
}

class PasswordValidator:
    def __init__(self):
        self.min_length = 8
        self.require_uppercase = True
        self.require_lowercase = True
        self.required_numbers = True
        self.require_symbols = False
        self.common_passwords = [
            '123456', 'password', '12345678', 'qwerty',
            '123456789', '12345', '1234', '111111',
            '1234567', 'dragon', '123123', 'baseball'
        ]

    def validate(self, password: str):
        issues = []
        score = 0
        # 长度检查
        if len(password) < self.min_length:
            issues.append(f'密码长度至少{self.min_length}位')
        else:
            score += 25
        # 字符类型检查
        if self.require_uppercase and not any(c.isupper() for c in password):
            issues.append("密码必须包含大写字母")
        else:
            score += 15
        if self.require_lowercase and not any(c.islower() for c in password):
            issues.append('密码必须包含小写字母')
        else:
            score += 15
        if self.required_numbers and not any(c.isdigit() for c in password):
            issues.append('密码必须包含数字')
        else:
            score += 15

        if self.require_symbols and not any(not c.isalnum() for c in password):
            issues.append('密码必须包含特殊字符')
        else:
            score += 15
        # 常见密码检查
        if password.lower() in self.common_passwords:
            issues.append('密码过于常见，请使用更复杂密码')
            score = max(score - 20, 0)
        else:
            score += 10
        # 连续字符检查
        if self._has_sequential_chars(password):
            issues.append('密码包含连续的字符')
            score = max(score - 10, 0)
        # 重复字符检查
        if self._has_repeating_chars(password):
            issues.append('密码包含重复字符')
            score = max(score - 10, 0)
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'score': min(score, 100),
            'strength': self._get_strength_level(score)
        }

    def _has_sequential_chars(self, password):
        sequences = ['abcdefghijklmnopqrstuvwxyz', '0123456789', 'qwertyuiop']
        password_lower = password.lower()
        for seq in sequences:
            for i in range(len(seq) - 2):
                if seq[i:i + 3] in password_lower:
                    return True
        return False

    def _has_repeating_chars(self, password: str):
        # 检查连续重复字符
        for i in range(len(password) - 2):
            if password[i] == password[i + 1] == password[i + 2]:
                return True
        # 检查模式重复
        if len(password) >= 6:
            for i in range(len(password) - 5):
                chunk = password[i:i + 3]
                if chunk in password[i + 3:]:
                    return True
        return False

    def _get_strength_level(self, score: int):
        if score >= 80:
            return 'very_strong'
        elif score >= 60:
            return 'strong'
        elif score >= 40:
            return 'medium'
        elif score >= 20:
            return 'weak'
        else:
            return 'very_weak'


class SecurityManager:
    '''安全管理'''

    def __init__(self):
        self.password_validator = PasswordValidator()

    @staticmethod
    def generate_secret_key():
        '''生成安全密钥'''
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_jwt_secret():
        '''生成jwt密钥（修正拼写错误：原geneerate_jwt_secret）'''
        return secrets.token_hex(32)

    @staticmethod
    def hash_password_bcrypt(password: str) -> Tuple[str, str]:
        '''使用bcrypt哈希密码（指定rounds，修复原逻辑错误）'''
        password_bytes = password.encode('utf-8')
        # 指定rounds=14，替代默认12，提升加密强度
        salt = bcrypt.gensalt(rounds=SECURITY_CONFIG["bcrypt_rounds"])
        password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
        # salt嵌入在bcrypt哈希中，此处返回哈希即可（也可拆分返回）
        return password_hash, salt.decode('utf-8')

    @staticmethod
    def hash_password_pbkdf2(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        '''使用PBKDF2哈希密码（提升迭代次数，增强强度）'''
        if salt is None:
            salt = secrets.token_hex(16)
        try:
            # 提升迭代次数至20万（原10万），增强加密强度
            password_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                SECURITY_CONFIG["pbkdf2_iterations"]  # 可配置迭代次数
            ).hex()
            return password_hash, salt
        except Exception as e:
            # 捕获编码/参数异常，避免崩溃
            current_app.logger.error(f"PBKDF2哈希密码失败: {str(e)}")
            raise ValueError("密码哈希处理失败") from e

    @staticmethod
    def verify_password(
            password: str,
            password_hash: str,
            salt: Optional[str] = None,
            hash_type: str = "pbkdf2"  # 支持bcrypt/pbkdf2两种验证
    ) -> bool:
        '''
        验证密码（修复安全错误：处理无效哈希，避免接口崩溃）
        :param password: 原始密码
        :param password_hash: 哈希值
        :param salt: 盐（PBKDF2需要，bcrypt无需传）
        :param hash_type: 哈希类型（pbkdf2/bcrypt）
        :return: 是否验证通过
        '''
        try:
            if hash_type == "bcrypt":
                # bcrypt验证逻辑
                password_bytes = password.encode('utf-8')
                hash_bytes = password_hash.encode('utf-8')
                return bcrypt.checkpw(password_bytes, hash_bytes)
            elif hash_type == "pbkdf2":
                # PBKDF2验证逻辑
                if not salt:
                    current_app.logger.warning("PBKDF2验证密码缺少salt")
                    return False
                # 检查哈希长度是否符合sha256输出（64字符）
                if len(password_hash) != 64:
                    current_app.logger.warning("无效的PBKDF2哈希长度")
                    return False
                computed_hash, _ = SecurityManager.hash_password_pbkdf2(password, salt)
                return computed_hash == password_hash
            else:
                current_app.logger.error(f"不支持的哈希类型: {hash_type}")
                return False
        except (ValueError, TypeError, UnicodeEncodeError, bcrypt.InvalidHashError) as e:
            # 捕获所有可能的异常：无效哈希、编码错误、参数错误等
            current_app.logger.error(f"验证密码失败（无效哈希/参数）: {str(e)}")
            return False  # 返回False而非抛异常，保证接口稳定性
        except Exception as e:
            # 兜底捕获未知异常
            current_app.logger.critical(f"密码验证未知异常: {str(e)}")
            return False

    @staticmethod
    def generate_jwt_token(
            user_id: int,
            token_type: str = "access",  # access/refresh/reset 区分令牌类型
            expires_in: Optional[int] = None
    ) -> str:
        '''
        生成JWT令牌（修复逻辑错误：区分access/refresh token过期时间）
        :param user_id: 用户ID
        :param token_type: 令牌类型（access/refresh/reset）
        :param expires_in: 自定义过期时间（秒），优先级高于默认值
        :return: JWT令牌
        '''
        # 按令牌类型设置默认过期时间
        if expires_in is None:
            if token_type == "access":
                # access_token：15分钟过期（短时效）
                expires_in = SECURITY_CONFIG["access_token_expire_minutes"] * 60
            elif token_type == "refresh":
                # refresh_token：7天过期（长时效）
                expires_in = SECURITY_CONFIG["refresh_token_expire_days"] * 24 * 3600
            elif token_type == "reset":
                # 重置令牌：1小时过期
                expires_in = SECURITY_CONFIG["reset_token_expire_hours"] * 3600
            else:
                raise ValueError(f"不支持的令牌类型: {token_type}")

        payload = {
            "user_id": user_id,
            "token_type": token_type,
            "exp": datetime.utcnow() + timedelta(seconds=expires_in),
            "iat": datetime.utcnow()
        }
        try:
            return jwt.encode(
                payload,
                current_app.config['SECRET_KEY'],
                algorithm='HS256'
            )
        except Exception as e:
            current_app.logger.error(f"生成JWT令牌失败: {str(e)}")
            raise RuntimeError("令牌生成失败") from e

    @staticmethod
    def verify_jwt_token(token: str, token_type: Optional[str] = None) -> Union[int, None]:
        '''
        验证JWT令牌（支持校验令牌类型）
        :param token: JWT令牌
        :param token_type: 期望的令牌类型（如access/refresh）
        :return: 用户ID（验证通过）/None（验证失败）
        '''
        try:
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )
            # 校验令牌类型（可选）
            if token_type and payload.get("token_type") != token_type:
                current_app.logger.warning(f"令牌类型不匹配：期望{token_type}，实际{payload.get('token_type')}")
                return None
            # 修正原拼写错误：rest_password -> user_id
            return payload.get('user_id')
        except jwt.ExpiredSignatureError:
            current_app.logger.warning("JWT令牌已过期")
            return None
        except jwt.InvalidTokenError as e:
            current_app.logger.warning(f"无效的JWT令牌: {str(e)}")
            return None
        except Exception as e:
            current_app.logger.error(f"验证JWT令牌未知异常: {str(e)}")
            return None

    @staticmethod
    def generate_api_key():
        '''生成api密钥'''
        return secrets.token_urlsafe(32)

    @staticmethod
    def sanitize_filename(filename: str):
        '''清理文件名，防止路径遍历攻击'''
        # 移除路径分隔符
        filename = os.path.basename(filename)
        # 只允许字母、数字、下划线、点、连字符
        filename = re.sub(r'[^\w\.\-]', '_', filename)
        # 修正长度限制逻辑（原25应为255）
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255 - len(ext)] + ext
        return filename

    @staticmethod
    def validate_email(email: str):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_username(username: str):
        if not username or len(username) < 3 or len(username) > 20:
            return False
        # 只允许字母、数字、下划线
        pattern = r'^[a-zA-Z0-9_]+$'
        return bool(re.match(pattern, username))

    @staticmethod
    def generate_csrf_token():
        return secrets.token_hex(32)


# 创建安全管理器实例
security_manager = SecurityManager()
password_validator = PasswordValidator()
