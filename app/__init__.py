from core.database import db
from core.extensions import bcrypt, jwt

__version__ = "0.1.0"


def create_app(*args, **kwargs):
    """延迟导入 `create_app`，避免在包导入时触发循环依赖。"""
    from core.factory import create_app as _create_app
    return _create_app(*args, **kwargs)


__all__ = ["create_app", "db", "bcrypt", "jwt", "__version__"]
