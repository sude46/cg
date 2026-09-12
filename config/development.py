import logging
import os
import secrets
from urllib.parse import quote_plus

from dotenv import load_dotenv

from .base import BaseConfig

load_dotenv()

class DevelopmentConfig(BaseConfig):
	'''开发环境配置'''
	DEBUG = True
	SQLALCHEMY_ECHO = True

	# 为避免在配置模块引用应用代码（导致循环导入），在此处使用基础分页默认值
	PAGE_SIZE_DEFAULT = 20
	PAGE_NUM_DEFAULT = 1

	#开发环境数据库
	@property
	def SQLALCHEMY_DATABASE_URI(self):
		db_url = os.getenv('DATABASE_URL') or os.getenv('DEV_DATABASE_URL')
		if db_url:
			return self._sanitize_db_url(db_url)
		#开发环境默认配置
		mysql_host=os.getenv('MYSQL_HOST','localhost')
		mysql_user=os.getenv('MYSQL_USER')
		mysql_password=os.getenv('MYSQL_PASSWORD')
		mysql_db=os.getenv('MYSQL_DB')

		missing_configs=[]
		if not mysql_user:
			missing_configs.append('MYSQL_USER')
		if not mysql_db:
			missing_configs.append('MYSQL_DB')
		if missing_configs:
			raise OSError(
				f"开发环境数据库配置缺失：{', '.join(missing_configs)}，请通过环境变量设置"
			)

		mysql_password=self._validate_dev_password(mysql_password)

		#构建安全的连接字符串
		return self._build_db_uri(mysql_host,mysql_user,mysql_password,mysql_db)
	def _sanitize_db_url(self, db_url: str):
		"""清理数据库URL,移除敏感信息"""
		if '://' in db_url:
			scheme, rest = db_url.split('://', 1)
			if '@' in rest:
				user_part, host_part = rest.split('@', 1)
				if '/' in host_part:
					host, db_path = host_part.split('/', 1)
				else:
					host, db_path = host_part, ''
				# 打印时使用脱敏后的 host 信息
				safe = f"{scheme}://***@{host}/{db_path}"
				print(f'使用数据库:{safe}')
		# 返回原始 db_url 以供实际连接使用
		return db_url
	def _validate_dev_password(self, password: str):
		if not password:
			random_password = secrets.token_hex(8)
			print(f'警告:使用随机生成的开发数据库密码:{random_password}')
			print('建议设置MYSQL_PASSWORD环境变量')
			return random_password
		# 检查是否使用弱密码
		weak_passwords = ['', 'password', '123456', 'root', 'admin']
		if password in weak_passwords:
			print(f"警告：使用了弱密码'{password}',建议使用更强的密码")
		return password
	def _build_db_uri(self, host: str, user: str, password: str, database: str):
		"""安全地构建数据库 URI（对密码进行 URL 编码）。
		为常见 MySQL 驱动使用 `mysql+pymysql://`，可根据依赖调整。
		"""
		encoded_password = quote_plus(password)
		uri = f'mysql+pymysql://{user}:{encoded_password}@{host}/{database}'
		return uri
	SESSION_COOKIE_SECURE=False
	PROPAGATE_EXCEPTIONS=True

	@classmethod
	def init_app(cls,app):
		BaseConfig.init_app(app)
		cls._check_development_security(app)
		cls._setup_development_loging()
	@classmethod
	def _setup_development_loging(cls):
		# 根日志级别设为INFO，减少基础冗余日志
		logging.basicConfig(
			level=logging.INFO,
			format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
			datefmt='%Y-%m-%d %H:%M:%S'
		)
		# 单独设置SQLAlchemy的日志级别为DEBUG（仅输出SQL语句，不冗余打印其他日志）
		sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
		sqlalchemy_logger.setLevel(logging.DEBUG)
		# 关闭其他冗余模块的DEBUG日志
		for logger_name in ['werkzeug', 'urllib3', 'chardet']:
			logging.getLogger(logger_name).setLevel(logging.WARNING)
	@classmethod
	def _check_development_security(cls,app):
		warnings = []
		if app.config.get('SECRET_KEY') and 'dev-key' in app.config.get('SECRET_KEY'):
			warnings.append('使用默认开发密钥，生产环境设置SECRET_KEY')
		if app.config.get('JWT_SECRET_KEY') and 'jwt-dev-key' in app.config.get('JWT_SECRET_KEY'):
			warnings.append('使用默认JWT开发密钥，生产环境设置JWT_SECRET_KEY')
		db_uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
		if ':@localhost' in db_uri or ':@127.0.0.1' in db_uri:
			warnings.append('数据库使用空密码或默认密码')
		if warnings:
			for w in warnings:
				print(f'{w}')

