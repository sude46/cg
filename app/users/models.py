from datetime import datetime,timezone
from time import time
from typing import Optional
from flask import current_app
import pyotp
from core.database import db
from core.extensions import bcrypt
# 修正1：pyotp导入异常处理
try:
    import pyotp
except ImportError:
    pyotp = None  # 降级处理，避免应用崩溃


try:
    import jwt  # type: ignore[import]  # PyJWT library
except ImportError:  # pragma: no cover
    # Fallback stub for static analysis when PyJWT is not installed
    class jwt:  # type: ignore[no-redef]
        @staticmethod
        def encode(*args, **kwargs):
            raise RuntimeError("PyJWT is required but not installed")

        @staticmethod
        def decode(*args, **kwargs):
            raise RuntimeError("PyJWT is required but not installed")

class User(db.Model):
	__tablename__='users'

	id=db.Column(db.Integer,primary_key=True)
	username=db.Column(db.String(64),unique=True,nullable=False,index=True)
	email=db.Column(db.String(120),unique=True,nullable=False,index=True)
	password_hash=db.Column(db.String(128),nullable=False)
	is_active=db.Column(db.Boolean,default=True)
	is_admin=db.Column(db.Boolean,default=False)
	created_at=db.Column(db.DateTime,default=lambda:datetime.now(timezone.utc))
	last_login=db.Column(db.DateTime)
	# 密码历史（存储最近5次密码哈希，用逗号分隔，最多存储5个）
	password_history=db.Column(db.Text,default='')
	#登陆失败次数（用于限流）
	login_fail_count=db.Column(db.Integer,default=0,nullable=False)
	#账号锁定时间（达到失败阈值后，记录锁定截止时间）
	lock_until=db.Column(db.DateTime,nullable=True)
	#MFA相关字段
	mfa_secret=db.Column(db.String(20),nullable=True) #MFA密钥
	mfa_enabled=db.Column(db.Boolean,default=False,nullable=False) #是否启用MFA

	posts=db.relationship('Post',back_populates='author',lazy='dynamic')
	comments=db.relationship('Comment',back_populates='author',lazy='dynamic')
	likes=db.relationship('Like',back_populates='user',lazy='dynamic')

	followers=db.relationship(
		'Follow',
		foreign_keys='Follow.followed_id',
		back_populates='followed',
		lazy='dynamic'
		)
	following=db.relationship(
		'Follow',
		foreign_keys='Follow.follower_id',
		back_populates='follower',
		lazy='dynamic'
 		)
	def set_password(self,password:str):
		'''设置密码'''
		# 1. 生成新密码哈希
		new_hash = bcrypt.generate_password_hash(password).decode('utf-8')
		# 2. 获取当前密码历史（拆分）
		history_hashes = self.password_history.split(",") if self.password_history else []
		# 3. 移除空值，保持最多5条
		history_hashes = [h for h in history_hashes if h]
		if self.password_hash:
			history_hashes.insert(0,self.password_hash)
		# 5. 截断为最多5条
		history_hashes = history_hashes[:5]
		# 6. 更新密码和历史
		self.password_hash = new_hash
		self.password_history = ",".join(history_hashes)
	
	
	def check_password(self,password:str)->bool:
		return bcrypt.check_password_hash(self.password_hash,password)
	def get_reset_token(self,expires_in:int=600)->str:
		return jwt.encode(
			{'reset_password':self.id,'exp':time()+expires_in},
			current_app.config['SECRET_KEY'],
			algorithm='HS256'
			)
	@staticmethod
	def verify_reset_token(token:str):
		try:
			id=jwt.decode(
				token,
				current_app.config['SECRET_KEY'],
				algorithms=['HS256']
				)['reset_password']
		except:
			return None
		return User.query.get(id)
	

	def to_dict(self):
		from .schemas import UserSchema
		user_schema = UserSchema()
		return user_schema.dump(self)
		
	def is_password_reused(self, new_password) -> bool:	
		"""检查新密码是否在密码历史中被重用"""
		if not self.password_history:
			return False
		history_hashes = self.password_history.split(",")
		for pwd_hash in history_hashes:
			if bcrypt.check_password_hash(pwd_hash, new_password):
				return True
		return False
	# ---------------------- 账号锁定相关方法 ----------------------
	def is_account_locked(self) -> bool:
		if self.lock_until is None:
			return False
		return datetime.now() < self.lock_until
	# ---------------------- 多因素认证（MFA）相关方法 ----------------------	

	def generate_mfa_secret(self):
		if pyotp is None:
			raise RuntimeError("pyotp is required but not installed")
		self.mfa_secret = pyotp.random_base32(length=16)
		return self.mfa_secret
	def verify_mfa_code(self, mfa_code):
		if pyotp is None:
			raise RuntimeError("pyotp is required but not installed")
		if not self.mfa_secret or not self.mfa_enabled:
			return False
		totp = pyotp.TOTP(self.mfa_secret)
		return totp.verify(mfa_code, valid_window=1)
	def __repr__(self):
		return f'<User{self.username}>'

