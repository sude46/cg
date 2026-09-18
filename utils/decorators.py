import logging
from functools import wraps

from flask import g, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError as MarshmallowValidationError

from app.common.exceptions import (
    ValidationError,
)
from utils.response import ResponseCode, fail_response

logger = logging.getLogger(__name__)


def inject_current_user(f):
    """注入当前用户ID到g对象，替代重复的get_jwt_identity()"""
    @wraps(f)
    @jwt_required()
    def wrapper(*args, **kwargs):
        g.current_user_id = get_jwt_identity()
        return f(*args, **kwargs)
    return wrapper


def validate_json(schema_class):
    """
    统一入参校验装饰器（基于 Marshmallow Schema）
    功能：拦截请求，解析JSON，使用Schema校验入参，合法数据挂载到 g.validated_json
    :param schema_class: Marshmallow 定义的 RequestSchema 类（入参专用）
    :return: 校验通过则进入路由，失败则直接返回 400 错误
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                json_data = request.get_json()
                if json_data is None:
                    raise ValidationError("请求必须是JSON格式")
            except Exception:
                return fail_response(ResponseCode.VALIDATION_ERROR, "请求体不能为空，且必须为JSON格式"), 400

            try:
                schema = schema_class() if isinstance(schema_class, type) else schema_class
                validated_data = schema.load(json_data)
                g.validated_json = validated_data
                logger.debug(f"入参校验成功: {validated_data}")
            except MarshmallowValidationError as e:
                error_detail = e.messages
                return fail_response(ResponseCode.VALIDATION_ERROR, f"参数校验失败:{error_detail}"), 400
            except ValidationError as e:
                return fail_response(ResponseCode.VALIDATION_ERROR, f"参数校验失败:{str(e)}"), 400
            except Exception as e:
                logger.error(f"参数校验内部错误: {str(e)}", exc_info=True)
                return fail_response(ResponseCode.INTERNAL_ERROR, "服务器内部错误"), 500
            return f(*args,**kwargs)
        return wrapper
    return decorator


def transactional(rollback_on=None):
    """
    数据库事务装饰器：自动提交事务，异常时回滚

    用法：@transactional()
    def creat_something(...):...
    #或指定某些异常不需要回滚（极少用）
    @transactional(rollback_on=(Exception,))
    """
    #如果没有传参默认所有异常都会触发回滚
    if rollback_on is None:
        rollback_on=(Exception,)
    def decorator(f):
        @wraps(f)
        def wrapper(*args,**kwargs):
            from core.database import db
            try:
                #执行业务代码
                result=f(*args,**kwargs)
                #无异常，提交事务
                db.session.commit()
                return result
            except rollback_on as e:
                db.session.rollback()
                logger.warning(f'事务回滚[{f.__name__}]:{type(e).__name__}:{e}')
                raise
        return wrapper
    return decorator

def handle_errors(default_error_msg="操作失败", default_code=500):
    """
    统一异常处理装饰器：捕获异常并返回标准错误响应
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                from flask import current_app

                from utils.response import ResponseCode, fail_response
                current_app.logger.error(f"Unhandled error: {str(e)}", exc_info=True)
                return fail_response(ResponseCode.INTERNAL_ERROR, default_error_msg), default_code
        return wrapper
    return decorator

def ownership_required(model_class, resource_id_param):
    """
    资源所有权装饰器：验证当前用户是否为资源所有者
    model_class: SQLAlchemy 模型类
    resource_id_param: 路由中资源ID的参数名（如 'post_id'）
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask_jwt_extended import get_jwt_identity

            from app.common.exceptions import PermissionError
            from core.database import db

            resource_id = kwargs.get(resource_id_param)
            if not resource_id:
                raise PermissionError("资源ID不存在")

            user_id = get_jwt_identity()
            if not user_id:
                raise PermissionError("未认证")

            # 查询资源所有者
            instance = db.session.query(model_class).filter_by(id=resource_id).first()
            if not instance:
                from app.common.exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(f"{model_class.__name__}不存在")

            # 假设模型类有一个 user_id 或 owner_id 字段
            owner_id = getattr(instance, 'user_id', None) or getattr(instance, 'owner_id', None)
            if owner_id != user_id:
                raise PermissionError("无权操作此资源")

            return f(*args, **kwargs)
        return wrapper
    return decorator


