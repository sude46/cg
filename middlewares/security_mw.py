from flask import make_response


def init_security_headers(app):
    """添加全局安全响应头：HSTS、CSP、X-Frame-Options 等。"""

    @app.after_request
    def add_security_headers(response):
        # 防止点击劫持（仅允许同域嵌入可改为SAMEORIGIN，根据业务调整）
        if 'X-Frame-Options' not in response.headers:  # 避免覆盖已有配置
            response.headers['X-Frame-Options'] = 'DENY'
        
        # 防止 MIME 类型嗅探
        if 'X-Content-Type-Options' not in response.headers:
            response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # 启用 HSTS（仅HTTPS，增加preload并校验配置）
        if app.config.get('HTTPS_ONLY', False):
            hsts_value = 'max-age=31536000; includeSubDomains'
            if app.config.get('HSTS_PRELOAD', False):
                hsts_value += '; preload'
            if 'Strict-Transport-Security' not in response.headers:
                response.headers['Strict-Transport-Security'] = hsts_value
        
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "  
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://trusted-cdn.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "  # 替代X-Frame-Options（CSP级别更强）
            "upgrade-insecure-requests;"  # 强制HTTPS
        )
        if 'Content-Security-Policy' not in response.headers:
            response.headers['Content-Security-Policy'] = csp_policy
        
        # 新增：防XSS基础头（补充）
        if 'X-XSS-Protection' not in response.headers:
            response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response


__all__ = ["init_security_headers"]
