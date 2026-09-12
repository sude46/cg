import time

from flask import g, request

from core.metrics import HTTP_LATENCY, HTTP_REQUESTS


def init_metrics_middleware(app):
    '''
    必须在所有中间件最先注册!
    这样before_request最早执行，after_request最晚执行计时最准
    '''
    @app.before_request
    def _metrics_before():
        g._weibo_metrics_start=time.time()

    @app.after_request
    def _metrics_after(response):
        if not hasattr(g,'_weibo_metrics_start'):
            return response
        latency=time.time()-g._weibo_metrics_start
        endpoint=request.endpoint or 'unknown'

        HTTP_REQUESTS.labels(
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code
                ).inc()
        HTTP_LATENCY.labels(
                method=request.method,
                endpoint=endpoint
                ).observe(latency)
        return response


