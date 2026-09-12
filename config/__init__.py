import inspect
import os
from typing import Any

from .base import BaseConfig
from .development import DevelopmentConfig
from .production import ProductionConfig
from .testing import TestingConfig

# 配置映射（统一配置类映射，避免重复逻辑）
CONFIG_MAPPING = {
    'development': DevelopmentConfig,
    'dev': DevelopmentConfig,
    'production': ProductionConfig,
    'prod': ProductionConfig,
    'testing': TestingConfig,
    'test': TestingConfig,
    'default': DevelopmentConfig
}

# 敏感配置字段列表（可根据实际业务扩展，覆盖所有敏感配置项）
SENSITIVE_FIELDS = {
    'SECRET_KEY', 'JWT_SECRET_KEY', 'MYSQL_PASSWORD', 'REDIS_PASSWORD',
    'MAIL_PASSWORD', 'DATABASE_URL', 'REDIS_URL', 'REDIS_CONN'
}

# 需排除的非配置属性（过滤方法、内置属性、特殊属性）
EXCLUDE_ATTRS = {
    'init_app', 'UPLOAD_FOLDER', 'LOG_DIR', 'INFO_LOG_FILE', 'ERROR_LOG_FILE',
    '__module__', '__doc__', '__dict__', '__weakref__', '__class__'
}

def get_config(config_name: str = None):
    # 如果传 None，从环境变量读取，兼容 APP_ENV 和 FLASK_ENV
    env = config_name or os.getenv("FLASK_ENV") or os.getenv("APP_ENV", "development")
    return CONFIG_MAPPING.get(env.lower(), DevelopmentConfig)



def _get_config_attributes(config_obj: BaseConfig) -> dict[str, Any]:
    """
    私有方法：提取配置类的所有有效属性（适配类级属性，解决__dict__缺失问题）
    :param config_obj: 配置实例（BaseConfig 及其子类实例）
    :return: 纯配置项字典（排除方法、特殊属性）
    """
    config_dict = {}
    # 遍历配置类及其所有父类的属性（覆盖继承的配置项）
    for cls in inspect.getmro(config_obj.__class__):
        if cls is object:  # 跳过顶层object类
            continue
        # 提取当前类的所有属性
        for attr_name, attr_value in cls.__dict__.items():
            # 过滤：排除特殊属性、方法、已排除项，仅保留普通配置属性
            if (
                attr_name not in EXCLUDE_ATTRS
                and not attr_name.startswith('_')
                and not inspect.isfunction(attr_value)
                and not inspect.ismethod(attr_value)
                and not isinstance(attr_value, classmethod)
                and not isinstance(attr_value, staticmethod)
            ):
                config_dict[attr_name] = attr_value
    return config_dict


def sanitize_config(config_obj: BaseConfig) -> dict[str, Any]:
    """
    配置脱敏方法：过滤敏感字段，避免日志泄露（适配BaseConfig无__dict__的场景）
    :param config_obj: BaseConfig 及其子类的配置实例
    :return: 脱敏后的配置字典
    """
    # 提取所有有效配置属性（核心修复点）
    config_dict = _get_config_attributes(config_obj)
    # 对敏感字段进行脱敏处理
    for key in SENSITIVE_FIELDS:
        if key in config_dict:
            config_dict[key] = '******'
    return config_dict


def load_config() -> BaseConfig:
    """加载对应环境的配置（兼容原有调用逻辑，增加动态性）"""
    return get_config()


__all__ = ['get_config', 'sanitize_config', 'load_config']


