from flask import current_app, g

from utils.snowflake_util import Snowflake


# ---------------------- 第一步：统一管理业务错误码 ----------------------
class ResponseCode:
    """响应业务码枚举（与 HTTP 状态码对应，方便前后端对接）"""
    SUCCESS = 200
    CREATED = 201
    PARAM_ERROR = 400  # 参数错误/格式错误
    UNAUTHORIZED = 401  # 未认证（未登录/Token失效）
    FORBIDDEN = 403  # 无权限操作
    RESOURCE_NOT_FOUND = 404  # 资源不存在
    CONFLICT_ERROR = 409  # 资源冲突（已点赞/已关注/用户名重复）
    SERVER_ERROR = 500  # 服务器内部错误
    VALIDATION_ERROR = 10001
    PERMISSION_DENIED = 10003
    AUTHENTICATION_FAILED = 10004
    INTERNAL_ERROR = 5000

# ---------------------- 第二步：生成请求唯一标识（用于问题追踪） ----------------------
def generate_request_id():
    """生成唯一request_id（替换原UUID，改用雪花算法）"""
    try:
        snowflake = Snowflake()  # 单例模式，无需重复初始化
        return str(snowflake.get_id())  # 转为字符串便于日志存储
    except Exception as e:
        import uuid
        fallback_id = str(uuid.uuid4()).replace("-", "")
        # 记录降级日志（需确保logger已初始化）
        import logging
        logging.warning(f"雪花算法生成request_id失败，降级为UUID: {e}")
        return fallback_id

# ---------------------- 第三步：封装核心响应函数 ----------------------
def success_response(data=None, message="操作成功"):
    """
    成功响应（统一格式）
    :param data: 业务数据（可选，默认空对象，支持任意格式：单个对象/列表/分页结构）
    :param message: 成功提示语（可选，默认"操作成功"）
    :return: 格式化后的成功响应体（可直接作为 Flask 接口返回值）
    """
    response_data = {
        "code": ResponseCode.SUCCESS,
        "data": data if data is not None else {},
        "message": message
    }

    # 日志记录（可选，便于调试，关联请求ID）
    request_id = getattr(g, "request_id", "unknown")
    current_app.logger.debug(f"[SUCCESS] request_id={request_id}, response={response_data}")

    return response_data

def fail_response(code, error_msg,details=None,request_id=None):
    """
    失败响应（统一格式）
    :param code: 业务错误码（参考 ResponseCode）
    :param error_msg: 人类可读的错误描述（前端展示用）
    :return: 格式化后的失败响应体
    """
    # 获取全局请求ID（若未生成，自动生成一个）
    request_id = request_id or getattr(g, "request_id", generate_request_id())

    response_data = {
        "code": code,
        "message": error_msg,
        "request_id": request_id
    }
    if details:
        response_data["details"]=details
    # 日志记录（错误级别，便于问题追踪）
    current_app.logger.error(f"[FAIL] request_id={request_id}, response={response_data}")

    return response_data


def build_pagination(page,per_page,total):
    """单一分页真源，结构固定"""
    page=max(1,int(page or 1))
    per_page=max(1,int(per_page or 20))
    total=max(0,int(total or 0))
    pages=(total+per_page-1)//per_page if total else 0
    return {
            "page":page,
            "per_page":per_page,
            "total":total,
            "pages":pages,
            "has_next":page<pages,
            "has_prev":page>1,
            }

def paginated_response(items,pagination,extra=None,message="操作成功"):
    """
    统一分页响应。
    -items:当前页对象列表
    -pagination:build_pagination/PaginationUtils.paginate的产物
    -extra:模块级元数据（如likeed_post_ids/unread_count/search_engine)
    """
    data={'items':items or [],"pagination":pagination or build_pagination(1,20,0)}
    if extra:
        data.update(extra)
    return success_response(data=data,message=message)

