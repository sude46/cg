import os
import logging
from app import create_app

# 1. 配置基础日志（便于调试/生产环境排查问题）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 2. 从环境变量读取配置名，默认使用开发环境配置
config_name = os.getenv("FLASK_CONFIG", "development")
logger.info(f"当前加载的Flask配置: {config_name}")

# 3. 初始化应用（显式传入配置名，确保配置加载生效）
app = create_app(config_name)

#=========prometheus指标端点==============
from flask import Response
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST

@app.route('/metrics')
def prometheus_metrics():
    '''Prometheus拉去端点'''
    return Response(generate_latest(),mimetype=CONTENT_TYPE_LATEST)


# 4. 从环境变量动态读取主机/端口，提升部署灵活性
HOST = os.getenv("FLASK_HOST", "0.0.0.0")
PORT = int(os.getenv("FLASK_PORT", 5000))

if __name__ == '__main__':
    # 5. 生产环境提示（禁用内置开发服务器）
    if config_name == "production":
        logger.warning(
            "⚠️ 生产环境请勿使用app.run()！建议使用WSGI服务器：\n"
            "gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app"
        )
    try:
        # 6. 仅开发环境启用debug，生产环境关闭（安全+性能）
        app.run(host=HOST, port=PORT, debug=(config_name != "production"))
    except Exception as e:
        logger.error(f"应用启动失败: {str(e)}", exc_info=True)
        raise
