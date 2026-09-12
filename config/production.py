import os
from datetime import timedelta

from dotenv import load_dotenv

from .base import BaseConfig

load_dotenv()

class ProductionConfig(BaseConfig):
	DEBUG=False
	SQLALCHEMY_ECHO=False

	# 生产环境必须提供完整的 URL。Flask-SQLAlchemy 使用的键名为 SQLALCHEMY_DATABASE_URI
	@property
	def SQLALCHEMY_DATABASE_URI(self):
		db_url = os.getenv('DATABASE_URL')
		if not db_url:
			raise ValueError("生产环境必须设置DATABASE_URL变量")
		return db_url
	@property
	def REDIS_PORT(self):
		try:
			return int(os.getenv("REDIS_PORT"))
		except (TypeError, ValueError):
			raise ValueError("生产环境 REDIS_PORT 必须是有效整数")

	@property
	def REDIS_PASSWORD(self):
		pwd = os.getenv("REDIS_PASSWORD")
		if not pwd:
			raise ValueError("生产环境必须配置 REDIS_PASSWORD 环境变量")
		return pwd

	#生产环境必须强制要求安全密钥
	@property
	def SECRET_KEY(self):
		secret_key = os.getenv('SECRET_KEY')
		if not secret_key:
			raise ValueError('生产环境必须设置SECRET_KEY环境变量')
		if 'dev-key' in secret_key:
			raise ValueError('生产环境不能使用开发密钥')
		return secret_key

	@property
	def JWT_SECRET_KEY(self):
		jwt_secret = os.getenv('JWT_SECRET_KEY')
		if not jwt_secret:
			raise ValueError("生产环境必须设置JWT_SECRET_KEY环境变量")
		if 'jwt-dev-key' in jwt_secret:
			raise ValueError("生产环境不能使用开发JWT密钥")
		return jwt_secret

	# 生产环境JWT过期时间可缩短（比如30分钟）
	JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)

	# ========== 覆盖：CORS配置（生产环境限制域名） ==========
	# 不要用/*，指定前端真实域名，比如：
	CORS_RESOURCES = {
		r"/api/*": {
			"origins": ["https://your-frontend-domain.com"],
			"supports_credentials": True
		}
	}


	# 生产环境安全配置
	SESSION_COOKIE_SECURE=True
	SESSION_COOKIE_HTTPONLY=True
	SESSION_COOKIE_SAMESITE='Lax'

	# 生产环境性能配置
	JSONIFY_PRETTYPRINT_REGULAR = False

	# 生产环境按机器性能调整：CPU 性能强则设 13-14，性能一般则保持 12
	BCRYPT_LOG_ROUNDS = 13  # 生产环境推荐值（需压测后微调）
	# 生产环境登录极限配置（更严格）
	LOGIN_MAX_ATTEMPTS = 3  # 生产环境登录失败次数更严格
	LOGIN_LOCK_DURATION = 600  # 锁定时长延长至 10 分钟

	@classmethod
	def init_app(cls,app):
		'''生产环境特定初始化'''
		BaseConfig.init_app(app)
		#生产环境日志配置
		import logging
		from logging.handlers import RotatingFileHandler
		#创建日志目录
		log_dir=os.path.join(os.path.dirname(__file__),'../logs')
		if not os.path.exists(log_dir):
			os.makedirs(log_dir)

		#文件日志处理器
		file_handler=RotatingFileHandler(
				os.path.join(log_dir,'weibo_platform.log'),
				maxBytes=10485760,
				backupCount=10)
		file_handler.setLevel(logging.INFO)
		file_handler.setFormatter(logging.Formatter(
				'%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
		app.logger.addHandler(file_handler)
		app.logger.setLevel(logging.INFO)

		#安全头中间件
		@app.after_request
		def set_security_headers(response):
			response.headers['X-Content-Type-Options']='nosniff'
			response.headers['X-Frame-Options']='DENY'
			response.headers['X-XSS-Protection']='1;mode=block'
			response.headers['Strict-Transport-Security'] = 'max-age=31536000;includeSubDomains'
			return response
