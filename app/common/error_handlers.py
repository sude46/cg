from flask import Flask, jsonify, g
import logging
import time
from app.common.exceptions import (
    BaseError,
    ValidationError,
    ResourceNotFoundError,
    PermissionError,
    AuthenticationError,
    DatabaseError,
    RateLimitError
)

def _get_log_extra():
    """封装日志上下文获取逻辑，避免重复代码"""
    elapsed_time = round(time.time() - g.get("request_start_time", time.time()), 3)
    return {
        "elapsed_time": elapsed_time,
        "request_id": g.get("request_id", "N/A"),
        "user_id": g.get("user_id", "N/A")
    }

def handle_base_error(e: BaseError):
    """处理所有自定义基础异常（保留原有逻辑，补充日志）"""
    # 补充自定义异常的日志记录
    log_extra = _get_log_extra()
    logger = logging.getLogger("flask.app")
    logger.warning(
        f"[CUSTOM ERROR] request_id={log_extra['request_id']}, error_code={e.error_code}, msg={e.message}",
        extra=log_extra
    )
    
    response = jsonify(e.to_dict())
    response.status_code = e.status_code
    return response

def handle_404_error(e):
    """处理404异常，转为自定义ResourceNotFoundError"""
    e = ResourceNotFoundError(message='访问的接口/资源不存在')
    return handle_base_error(e)  # 复用自定义异常处理逻辑

def handle_405_error(error):
    """处理405异常，转为自定义BaseError"""
    e = BaseError(
        message='请求方法不被允许',
        status_code=405,
        error_code=10007,
        details={"allowed_methods": error.description.split()[-1].strip('()')}
    )
    return handle_base_error(e)  # 复用自定义异常处理逻辑

def handle_global_exception(e: Exception):
    """统一处理所有未预期的全局异常（整合原有两套逻辑）"""
    log_extra = _get_log_extra()
    logger = logging.getLogger("flask.app")
    
    # 记录完整异常日志（含堆栈）
    logger.error(
        f"[UNEXPECTED EXCEPTION] request_id={log_extra['request_id']}, error={str(e)}",
        exc_info=True,  # 必须保留，否则看不到堆栈信息
        extra=log_extra
    )
    
    # 区分环境返回错误信息（开发环境显示详情，生产环境隐藏）
    if logger.level == logging.DEBUG:  # 开发/测试环境
        msg = str(e)
        error_code = 9999
    else:  # 生产环境
        msg = "Internal Server Error"
        error_code = 5000
    
    # 统一返回自定义格式（和BaseError保持一致）
    return jsonify({
        "code": error_code,
        "msg": msg,
        "request_id": log_extra["request_id"],
        "details": None
    }), 500

def register_error_handlers(app: Flask):
    """注册所有异常处理器"""
    # 1. 注册自定义异常（复用统一的handle_base_error）
    app.errorhandler(BaseError)(handle_base_error)
    app.errorhandler(ValidationError)(handle_base_error)
    app.errorhandler(ResourceNotFoundError)(handle_base_error)
    app.errorhandler(PermissionError)(handle_base_error)
    app.errorhandler(AuthenticationError)(handle_base_error)
    app.errorhandler(DatabaseError)(handle_base_error)
    app.errorhandler(RateLimitError)(handle_base_error)
    
    # 2. 注册HTTP标准异常
    app.errorhandler(404)(handle_404_error)
    app.errorhandler(405)(handle_405_error)
    
    # 3. 注册全局未预期异常（核心：覆盖视图+中间件所有场景）
    app.errorhandler(Exception)(handle_global_exception)
    # 关键补充：覆盖error_handler_spec，确保捕获所有异常
    app.error_handler_spec[None][Exception] = handle_global_exception
    
    app.logger.info(" 所有异常处理器注册完成")
