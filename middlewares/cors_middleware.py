from flask_cors import CORS


def init_cors(app):
    """统一初始化CORS：生产环境严格限制源，精细配置"""
    # 从配置读取允许的源（生产环境必须指定，禁止*）
    allowed_origins = app.config.get('CORS_ALLOWED_ORIGINS', [])
    CORS(
        app,
        origins=allowed_origins,  # 严格限制源
        methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],  # 允许的方法
        allow_headers=['Content-Type', 'Authorization', 'X-Request-ID'],  # 允许的请求头
        expose_headers=['X-Response-Time', 'X-Request-ID'],  # 暴露给前端的响应头
        supports_credentials=True,  # 允许携带Cookie（如需）
        max_age=86400  # 预检请求缓存时间（减少OPTIONS请求）
    )


__all__ = ["init_cors"]
