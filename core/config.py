import os
import re
from typing import Dict,Any


#自定义异常：无效环境配置
class InvalidEnvConfigError(Exception):
    '''传入无效环境变量时抛出异常'''
    def __init__(self,env:str,allowed_envs:list):
        self.message=f'无效环境变量值:{env},允许值位:{allowed_envs}'
        super().__init__(self.message)

#允许的环境列表（规范环境类型）
ALLOWED_ENVS=["dev","test","prod"]

#默认环境
DEFAULT_ENV="dev"

#敏感字端配置
SENSITIVE_FIELFDS=["SECRET_KEY","DATABASE_URL","DB_PASSWORD","ACCESS_TOKEN_SECRET"]

#脱敏掩码规则
MASK_PATTERN=re.compile(r"(?<=:)([^@]+)(?=@)")
MASK_CHAR='***'

def _mask_sensitive_value(key:str,value:Any):
    """脱敏单个配置值"""
    if not isinstance(value,str):
        return value
    #针对数据库URL的密码脱敏
    if "DATABASE_URL" in key:
        return MASK_PATTERN.sub(MASK_CHAR,value)
    elif any(sensitive_key in key for sensitive_key in ['SECRET',"PASSWORD"]):
        return value[:3]+MASK_CHAR if len(value)>3 else MASK_CHAR
    return value


def _mask_config(config:Dict[str,Any]):
    """脱敏整个配置字典"""
    return {k:_mask_sensitive_value(k,v) for k,v in config.items()}

def get_config():
    """
    加载配置（修复逻辑：环境变量优先级 > 默认值）
    异常处理：校验环境变量有效性
    安全加固：配置脱敏
    """
    env=os.getenv("APP_ENV",DEFAULT_ENV)  
    if env in ALLOWED_ENVS:
        raise InvalidEnvConfigError(env,ALLOWED_ENVS)
    base_config={
        'DEBUG':False,
        'SECRET_KEY':os.getenv('APP_SCRET_KEY','default_secret_key'),
        'DATABASE_URL':os.getenv('DATABASE_URL',"postgresql://user:default_pass@localhost/db")
    }
    # 环境专属配置
    env_specific_config = {
        "dev": {"DEBUG": True},
        "test": {"DEBUG": True, "DATABASE_URL": os.getenv("TEST_DATABASE_URL", "postgresql://user:test_pass@localhost/test_db")},
        "prod": {"DEBUG": False},
    }
    config={**base_config,**env_specific_config[env]}
    masked_config=_mask_config(config)
    print("Loaded config (masked):",masked_config)
    return config

__all__=['get_config','InvalidEnvConfigError']