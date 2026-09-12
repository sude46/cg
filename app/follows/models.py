
from app.common.database import utcnow
from core import db


class Follow(db.Model):
	__tablename__ = 'follows'

	id = db.Column(db.Integer, primary_key=True)
	follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
	followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
	created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
	deleted_at=db.Column(db.DateTime,nullable=True,default=None,index=True)


	#防重复用FollowService分布式锁+get_relation(lock=True)
	__table_args__ = (
			db.Index('idx_follow_relation','follower_id','followed_id'),
			db.Index('idx_follower_created','follower_id','deleted_at','created_at'),
			db.Index('idx_followed_created','followed_id','deleted_at','created_at'),
	)

				# 关系定义
	follower = db.relationship(
					'User', foreign_keys=[follower_id], back_populates='following', lazy='select'
				)
	followed = db.relationship(
					'User', foreign_keys=[followed_id], back_populates='followers', lazy='select'
				)

	def __repr__(self):
		return f'<Follow {self.follower_id}->{self.followed_id}>'

