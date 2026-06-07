from datetime import datetime,timezone
from app.common.database import utcnow
from time import time
from typing import Optional
from flask import current_app
import pyotp
from core.database import db
from core.extensions import bcrypt
import jwt


class PasswordHistory(db.Model):
	__tablename__='password_histories'
	id=db.Column(db.Integer,primary_key=True)
	user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False,index=True)
	password_hash=db.Column(db.String(128),nullable=False)
	created_at=db.Column(db.DateTime,default=utcnow,index=True)

	user=db.relationship('User',back_populates='password_histories')

class User(db.Model):
	__tablename__='users'

	id=db.Column(db.Integer,primary_key=True)
	username=db.Column(db.String(64),unique=True,nullable=False,index=True)
	email=db.Column(db.String(120),unique=True,nullable=False,index=True)
	password_hash=db.Column(db.String(128),nullable=False)
	is_active=db.Column(db.Boolean,default=True)
	is_admin=db.Column(db.Boolean,default=False)
	created_at=db.Column(db.DateTime,default=utcnow)
	last_login=db.Column(db.DateTime)
	is_deleted=db.Column(db.Boolean,default=False,nullable=False,index=True)

	following_count = db.Column(db.Integer, default=0, nullable=False)
	follower_count = db.Column(db.Integer, default=0, nullable=False)

	password_histories=db.relationship(
		'PasswordHistory',
		back_populates='user',
		lazy='dynamic',
		order_by='desc(PasswordHistory.created_at	)'
	)
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


