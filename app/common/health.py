"""健康检查端点：给compose healthcheck /负载均衡探针用
刻意不查DB/Redis --探针会高频打这个接口，引入接口，引入依赖等于给探针制造故障面"""
from flask import Blueprint

health_bp=Blueprint('health',__name__)

@health_bp.get('/health')
def health():
    return {'status':'ok'},200





