class BaseError(Exception):
    '''基础异常类，所有自定义异常的父类'''
    #默认HTTP状态码(500服务器内部错误)
    status_code=500
    #默认业务错误码(前端可根据错误码做差异化处理)
    error_code=10000
    #默认错误信息
    message='服务器内部错误'
    def __init__(
            self,
            message:str=None,
            status_code:int=None,
            error_code:int=None,
            details:dict=None
            ):
        super().__init__()
        #覆盖默认属性
        if message:
            self.message=message
        if status_code:
            self.status_code=status_code
        if error_code:
            self.error_code=error_code
        self.details=details or {}
    def to_dict(self)->dict:
        '''将一场转换为字典，方便接口返回json'''
        return{
                'error_code':self.error_code,
                'message':self.message,
                'details':self.details
                }
    def __str__(self)->str:
        return f'{self.message}(错误码:{self.error_code},详情:{self.details})'
class ValidationError(BaseError):
    '''参数验证失败异常'''
    status_code=400
    error_code=10001
    message='参数验证失败'
class ResourceNotFoundError(BaseError):
    '''资源不存在异常（如查询的用户，帖子，评论不存在）'''
    status_code=404
    error_code=10002
    message='请求的资源不存在'
class PermissionError(BaseError):
    '''权限不足异常'''
    status_code=403
    error_code=10003
    message='权限不足，无法执行该操作'
class AuthenticationError(BaseError):
    '''认证失败异常'''
    status_code=401
    error_code=10004
    message='认证失败，请先登录或刷新Token'
class DatabaseError(BaseError):
    '''数据库操作异常（如约束冲突，连接失败，事务提交失败）'''
    status_code=500
    error_code=10005
    message='数据库操作失败'
# 兼容历史拼写错误的别名，避免大量修改代码时破坏引用
DatabaseError = DatabaseError
class RateLimitError(BaseError):
    '''接口限流异常(如频繁请求接口触发限流)'''
    status_code=429
    error_code=10006
    message='请求过于频繁,请稍后再试'
class ConflictError(BaseError):
    '''资源冲突异常(如创建已存在的用户名，邮箱等)'''
    status_code=409
    error_code=10007
    message='资源冲突，操作无法完成'

class BusinessException(Exception):
    """业务逻辑异常（如参数错误、权限不足等）"""
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(self.message)

__all__ = [
    "BaseError",
    "ValidationError",
    "AuthenticationError",
    "PermissionError",
    "ResourceNotFoundError",
    "DatabaseError",
    "RateLimitError",
    "ConflictError"  
]
