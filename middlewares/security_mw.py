

def init_security_headers(app):
    """添加全局安全响应头：HSTS、CSP、X-Frame-Options 等。"""
    # 幂等：避免在 app 已处理请求后重复注册 after_request（Flask 会拒绝）
    if app.extensions.get('security_headers'):
        return
    app.extensions['security_headers'] = True

    @app.after_request
    def add_security_headers(response):

        if 'X-Frame-Options' not in response.headers:
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
        use_nonce=app.config.get('CSP_USE_NONCE', False)
        if use_nonce:
            import secrets
            nonce=secrets.token_urlsafe(16)
            response.headers['X-CSP-Nonce']=nonce
            script_src=f"'self' 'nonce-{nonce}' "
            style_src=f"'self' 'nonce-{nonce}' "
        else:
            # 警告：unsafe-inline 存在 XSS 风险，仅用于内联脚本无法避免的场景
            script_src="'self' 'unsafe-inline'"
            style_src="'self' 'unsafe-inline'"

        csp_policy = (
            f"default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src {style_src}; "
            f"img-src 'self' data: https:; "  # 允许 HTTPS 图片
            f"connect-src 'self'; "
            f"font-src 'self'; "
            f"frame-ancestors 'none'; "  # 替代 X-Frame-Options
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"upgrade-insecure-requests;"
        )
        if 'Content-Security-Policy' not in response.headers:
            response.headers['Content-Security-Policy'] = csp_policy

        # 新增：防XSS基础头（补充）
        if 'X-XSS-Protection' not in response.headers:
            response.headers['X-XSS-Protection'] = '1; mode=block'
        # 可选：Referrer 策略
        if 'Referrer-Policy' not in response.headers:
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        return response


__all__ = ["init_security_headers"]
